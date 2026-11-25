//! crt-stream: a video's raw frames through ONE librashader filter chain, kept for the whole video.
//!
//!   crt-stream --preset P.slangp --input WxH --output WxH [--params k=v,...] [--runtime metal|wgpu] [--warmup N]
//!
//! Raw RGBA8 frames of the input size come in on stdin, top row first; raw RGBA8 frames of the output size go out on
//! stdout, top row first. Frame n is drawn with frame count n, so feedback passes (crt-guest-advanced's afterglow),
//! the frame history and the frame count carry over from frame to frame, as in an emulator. librashader-cli draws
//! every frame as the first frame of a new chain instead.
//!
//! On stderr, as tools/crt/blender_crt.py writes them: `CRT_READY <runtime>; <adapter>; <seconds>` once the preset
//! is compiled, `CRT_FRAMES n` after each frame, `CRT_DONE n <seconds>` at the end.
//!
//! --warmup N draws the first frame N extra times first (frame counts 0 to N-1, not written out); the video's frames
//! then count on from N.

use anyhow::{Context, Result, anyhow, bail};
use librashader::ShortString;
use librashader::presets::{ShaderFeatures, ShaderPreset, WildcardContext};
use std::io::{ErrorKind, Read, Write};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::Instant;

struct Args {
    preset: PathBuf,
    input: (u32, u32),
    output: (u32, u32),
    params: Vec<(ShortString, f32)>,
    runtime: String,
    warmup: usize,
}

const USAGE: &str = "usage: crt-stream --preset P.slangp --input WxH --output WxH [--params k=v,...] \
                     [--runtime metal|wgpu] [--warmup N]";

fn default_runtime() -> &'static str {
    if cfg!(target_vendor = "apple") { "metal" } else { "wgpu" }
}

fn parse_size(s: &str) -> Result<(u32, u32)> {
    let (w, h) = s.split_once('x').ok_or_else(|| anyhow!("{s}: a size is WIDTHxHEIGHT"))?;
    let size = (w.parse()?, h.parse()?);
    if size.0 == 0 || size.1 == 0 {
        bail!("{s}: an empty size");
    }
    Ok(size)
}

fn parse_params(s: &str) -> Result<Vec<(ShortString, f32)>> {
    let mut out = Vec::new();
    for item in s.split(',').map(str::trim).filter(|x| !x.is_empty()) {
        let (k, v) = item.split_once('=').ok_or_else(|| anyhow!("{item}: a parameter is name=value"))?;
        out.push((ShortString::from(k.trim()), v.trim().parse::<f32>().map_err(|_| anyhow!("{item}: not a number"))?));
    }
    Ok(out)
}

fn parse_args() -> Result<Args> {
    let mut a = std::env::args().skip(1);
    let (mut preset, mut input, mut output, mut params) = (None, None, None, Vec::new());
    let (mut runtime, mut warmup) = (default_runtime().to_string(), 0);
    while let Some(flag) = a.next() {
        if flag == "--help" || flag == "-h" {
            println!("{USAGE}");
            std::process::exit(0);
        }
        if flag == "--version" || flag == "-V" {
            println!("crt-stream {} (librashader 0.12.1)", env!("CARGO_PKG_VERSION"));
            std::process::exit(0);
        }
        let value = a.next().ok_or_else(|| anyhow!("{flag} needs a value\n{USAGE}"))?;
        match flag.as_str() {
            "--preset" => preset = Some(PathBuf::from(value)),
            "--input" => input = Some(parse_size(&value)?),
            "--output" => output = Some(parse_size(&value)?),
            "--params" => params = parse_params(&value)?,
            "--runtime" => runtime = value,
            "--warmup" => warmup = value.parse().map_err(|_| anyhow!("--warmup {value}: not a number"))?,
            _ => bail!("unknown option {flag}\n{USAGE}"),
        }
    }
    let missing = |what: &str| anyhow!("{what} is needed\n{USAGE}");
    Ok(Args {
        preset: preset.ok_or_else(|| missing("--preset"))?,
        input: input.ok_or_else(|| missing("--input"))?,
        output: output.ok_or_else(|| missing("--output"))?,
        params,
        runtime,
        warmup,
    })
}

/// A runtime's filter chain with one frame in flight: `draw` submits a frame and hands back the one before it.
trait Drawer {
    /// "runtime; adapter", for CRT_READY.
    fn describe(&self) -> String;
    /// Upload `input`, draw it with `frame_count`, and if the previous frame was kept, read it into `out` and return
    /// true. `keep` says whether this frame will be read back.
    fn draw(&mut self, input: &[u8], frame_count: usize, keep: bool, out: &mut [u8]) -> Result<bool>;
    /// The last frame, if it was kept.
    fn finish(&mut self, out: &mut [u8]) -> Result<bool>;
}

fn load_preset(a: &Args) -> Result<ShaderPreset> {
    let mut context = WildcardContext::new();
    context.add_path_defaults(a.preset.as_path());
    ShaderPreset::try_parse_with_context(&a.preset, ShaderFeatures::NONE, context)
        .with_context(|| format!("can't read the preset {}", a.preset.display()))
}

fn set_params(parameters: &librashader::runtime::RuntimeParameters, params: &[(ShortString, f32)]) {
    if !params.is_empty() {
        parameters.update_parameters(|p| {
            for (k, v) in params {
                p.insert(k.clone(), *v);
            }
        });
    }
}

#[cfg(target_vendor = "apple")]
mod metal {
    use super::{Args, Drawer, load_preset, set_params};
    use anyhow::{Result, anyhow};
    use librashader::runtime::mtl::{FilterChain, FilterChainOptions};
    use librashader::runtime::{FilterChainParameters, Viewport};
    use objc2::rc::Retained;
    use objc2::runtime::ProtocolObject;
    use objc2_metal::{
        MTLBlitCommandEncoder, MTLCommandBuffer, MTLCommandEncoder, MTLCommandQueue, MTLCreateSystemDefaultDevice,
        MTLDevice, MTLOrigin, MTLPixelFormat, MTLRegion, MTLSize, MTLStorageMode, MTLTexture, MTLTextureDescriptor,
        MTLTextureUsage,
    };
    use std::ptr::NonNull;

    type Texture = Retained<ProtocolObject<dyn MTLTexture>>;

    pub struct Metal {
        device: Retained<ProtocolObject<dyn MTLDevice>>,
        queue: Retained<ProtocolObject<dyn MTLCommandQueue>>,
        chain: FilterChain,
        input: Texture,
        targets: [Texture; 2],
        size: (u32, u32),
        out_size: (u32, u32),
        next: usize,
        pending: Option<(Retained<ProtocolObject<dyn MTLCommandBuffer>>, usize, bool)>,
    }

    fn managed() -> bool {
        !cfg!(all(target_arch = "aarch64", target_vendor = "apple"))
    }

    fn texture(device: &ProtocolObject<dyn MTLDevice>, (w, h): (u32, u32), usage: MTLTextureUsage) -> Result<Texture> {
        unsafe {
            let desc = MTLTextureDescriptor::texture2DDescriptorWithPixelFormat_width_height_mipmapped(
                MTLPixelFormat::RGBA8Unorm,
                w as usize,
                h as usize,
                false,
            );
            desc.setSampleCount(1);
            desc.setStorageMode(if managed() { MTLStorageMode::Managed } else { MTLStorageMode::Shared });
            desc.setUsage(usage);
            device.newTextureWithDescriptor(&desc).ok_or_else(|| anyhow!("Metal couldn't make a {w}x{h} texture"))
        }
    }

    fn region((w, h): (u32, u32)) -> MTLRegion {
        MTLRegion {
            origin: MTLOrigin { x: 0, y: 0, z: 0 },
            size: MTLSize { width: w as usize, height: h as usize, depth: 1 },
        }
    }

    impl Metal {
        pub fn new(a: &Args) -> Result<Self> {
            let device = MTLCreateSystemDefaultDevice().ok_or_else(|| anyhow!("no Metal device"))?;
            let queue = device.newCommandQueue().ok_or_else(|| anyhow!("no Metal command queue"))?;
            let chain = FilterChain::load_from_preset(
                load_preset(a)?,
                &queue,
                Some(&FilterChainOptions { force_no_mipmaps: false }),
            )?;
            set_params(chain.parameters(), &a.params);
            let usage = MTLTextureUsage::ShaderRead | MTLTextureUsage::ShaderWrite | MTLTextureUsage::RenderTarget;
            let input = texture(&device, a.input, MTLTextureUsage::ShaderRead)?;
            let targets = [texture(&device, a.output, usage)?, texture(&device, a.output, usage)?];
            for t in &targets {
                if (t.width() as u32, t.height() as u32) != a.output {
                    return Err(anyhow!("Metal made the target {}x{}", t.width(), t.height()));
                }
            }
            Ok(Self { device, queue, chain, input, targets, size: a.input, out_size: a.output, next: 0, pending: None })
        }

        fn read(&self, slot: usize, out: &mut [u8]) {
            unsafe {
                self.targets[slot].getBytes_bytesPerRow_fromRegion_mipmapLevel(
                    NonNull::new(out.as_mut_ptr().cast()).unwrap(),
                    4 * self.out_size.0 as usize,
                    region(self.out_size),
                    0,
                );
            }
        }
    }

    impl Drawer for Metal {
        fn describe(&self) -> String {
            format!("metal; {}", self.device.name())
        }

        fn draw(&mut self, input: &[u8], frame_count: usize, keep: bool, out: &mut [u8]) -> Result<bool> {
            // The chain writes its uniforms into shared memory as it records, so a frame is only recorded once the
            // one before it is drawn. Reading that one back then overlaps with drawing this one.
            let prev = self.pending.take();
            if let Some((cmd, _, _)) = &prev {
                cmd.waitUntilCompleted();
            }
            unsafe {
                self.input.replaceRegion_mipmapLevel_withBytes_bytesPerRow(
                    region(self.size),
                    0,
                    NonNull::new(input.as_ptr() as *mut _).unwrap(),
                    4 * self.size.0 as usize,
                );
            }
            let slot = self.next;
            self.next ^= 1;
            let cmd = self.queue.commandBuffer().ok_or_else(|| anyhow!("no Metal command buffer"))?;
            let viewport = Viewport::new_render_target_sized_origin(self.targets[slot].as_ref(), None)?;
            self.chain.frame(&self.input, &viewport, cmd.as_ref(), frame_count, None)?;
            if keep && managed() {
                let blit = cmd.blitCommandEncoder().ok_or_else(|| anyhow!("no Metal blit encoder"))?;
                blit.synchronizeResource(self.targets[slot].as_ref());
                blit.endEncoding();
            }
            cmd.commit();
            self.pending = Some((cmd, slot, keep));
            Ok(match prev {
                Some((_, prev_slot, true)) => {
                    self.read(prev_slot, out);
                    true
                }
                _ => false,
            })
        }

        fn finish(&mut self, out: &mut [u8]) -> Result<bool> {
            Ok(match self.pending.take() {
                Some((cmd, slot, keep)) => {
                    cmd.waitUntilCompleted();
                    if keep {
                        self.read(slot, out);
                    }
                    keep
                }
                None => false,
            })
        }
    }
}

mod wgpu_runtime {
    use super::{Args, Drawer, load_preset, set_params};
    use anyhow::{Result, anyhow};
    use librashader::runtime::wgpu::{FilterChain, FilterChainOptions, WgpuOutputView};
    use librashader::runtime::{FilterChainParameters, Viewport};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicU8, Ordering};

    const FORMAT: wgpu::TextureFormat = wgpu::TextureFormat::Rgba8Unorm;

    struct Readback {
        buffer: wgpu::Buffer,
        // 0: idle, 1: mapping, 2: mapped, 3: failed
        state: Arc<AtomicU8>,
    }

    pub struct Wgpu {
        info: wgpu::AdapterInfo,
        device: wgpu::Device,
        queue: wgpu::Queue,
        chain: FilterChain,
        input: wgpu::Texture,
        target: wgpu::Texture,
        target_view: wgpu::TextureView,
        readbacks: [Readback; 2],
        size: (u32, u32),
        out_size: (u32, u32),
        padded_row: u32,
        next: usize,
        pending: Option<(wgpu::SubmissionIndex, usize, bool)>,
    }

    async fn adapter(instance: &wgpu::Instance) -> Result<wgpu::Adapter> {
        if std::env::var_os("WGPU_ADAPTER_NAME").is_some() {
            return Ok(wgpu::util::initialize_adapter_from_env_or_default(instance, None).await?);
        }
        Ok(instance
            .request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::from_env().unwrap_or(wgpu::PowerPreference::HighPerformance),
                compatible_surface: None,
                force_fallback_adapter: false,
                apply_limit_buckets: false,
            })
            .await?)
    }

    impl Wgpu {
        pub fn new(a: &Args) -> Result<Self> {
            pollster::block_on(Self::new_async(a))
        }

        async fn new_async(a: &Args) -> Result<Self> {
            let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::new_without_display_handle_from_env());
            let adapter = adapter(&instance).await?;
            let info = adapter.get_info();
            // As librashader-cli asks for them, but only those this adapter has: Metal has no pipeline cache
            let wanted = wgpu::Features::ADDRESS_MODE_CLAMP_TO_BORDER
                | wgpu::Features::PIPELINE_CACHE
                | wgpu::Features::TEXTURE_ADAPTER_SPECIFIC_FORMAT_FEATURES
                | wgpu::Features::FLOAT32_FILTERABLE;
            let features = adapter.features() & wanted;
            let max = a.output.0.max(a.output.1).max(a.input.0).max(a.input.1);
            let limits = wgpu::Limits {
                max_texture_dimension_2d: max.max(wgpu::Limits::default().max_texture_dimension_2d),
                ..wgpu::Limits::default()
            };
            let (device, queue) = adapter
                .request_device(&wgpu::DeviceDescriptor {
                    required_features: features,
                    required_limits: limits,
                    label: None,
                    ..Default::default()
                })
                .await?;
            let chain = FilterChain::load_from_preset(
                load_preset(a)?,
                &device,
                &queue,
                Some(&FilterChainOptions {
                    force_no_mipmaps: false,
                    enable_cache: features.contains(wgpu::Features::PIPELINE_CACHE),
                    adapter_info: Some(info.clone()),
                }),
            )?;
            set_params(chain.parameters(), &a.params);
            let texture = |(w, h): (u32, u32), usage| {
                device.create_texture(&wgpu::TextureDescriptor {
                    label: None,
                    size: wgpu::Extent3d { width: w, height: h, depth_or_array_layers: 1 },
                    mip_level_count: 1,
                    sample_count: 1,
                    dimension: wgpu::TextureDimension::D2,
                    format: FORMAT,
                    usage,
                    view_formats: &[FORMAT],
                })
            };
            let input = texture(a.input, wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST);
            let target = texture(a.output, wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC);
            if (target.width(), target.height()) != a.output {
                return Err(anyhow!("wgpu made the target {}x{}", target.width(), target.height()));
            }
            let target_view = target.create_view(&wgpu::TextureViewDescriptor::default());
            let align = wgpu::COPY_BYTES_PER_ROW_ALIGNMENT;
            let padded_row = (4 * a.output.0).div_ceil(align) * align;
            let readback = || Readback {
                buffer: device.create_buffer(&wgpu::BufferDescriptor {
                    label: None,
                    size: padded_row as u64 * a.output.1 as u64,
                    usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
                    mapped_at_creation: false,
                }),
                state: Arc::new(AtomicU8::new(0)),
            };
            let readbacks = [readback(), readback()];
            Ok(Self {
                info,
                device,
                queue,
                chain,
                input,
                target,
                target_view,
                readbacks,
                size: a.input,
                out_size: a.output,
                padded_row,
                next: 0,
                pending: None,
            })
        }

        fn collect(&mut self, index: wgpu::SubmissionIndex, slot: usize, out: &mut [u8]) -> Result<()> {
            self.device.poll(wgpu::PollType::Wait { submission_index: Some(index), timeout: None })?;
            let rb = &self.readbacks[slot];
            while rb.state.load(Ordering::Acquire) == 1 {
                self.device.poll(wgpu::PollType::Wait { submission_index: None, timeout: None })?;
            }
            if rb.state.load(Ordering::Acquire) != 2 {
                return Err(anyhow!("wgpu couldn't map the frame for reading"));
            }
            {
                let mapped = rb.buffer.get_mapped_range(..)?;
                let row = 4 * self.out_size.0 as usize;
                for (y, chunk) in mapped.chunks(self.padded_row as usize).enumerate() {
                    out[y * row..(y + 1) * row].copy_from_slice(&chunk[..row]);
                }
            }
            rb.buffer.unmap();
            rb.state.store(0, Ordering::Release);
            Ok(())
        }
    }

    impl Drawer for Wgpu {
        fn describe(&self) -> String {
            format!("wgpu {}; {}", format!("{:?}", self.info.backend).to_lowercase(), self.info.name)
        }

        fn draw(&mut self, input: &[u8], frame_count: usize, keep: bool, out: &mut [u8]) -> Result<bool> {
            self.queue.write_texture(
                self.input.as_image_copy(),
                input,
                wgpu::TexelCopyBufferLayout { offset: 0, bytes_per_row: Some(4 * self.size.0), rows_per_image: None },
                self.input.size(),
            );
            let slot = self.next;
            self.next ^= 1;
            let mut cmd = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: None });
            let output = WgpuOutputView::new_from_raw(&self.target_view, self.target.size().into(), FORMAT);
            let viewport = Viewport::new_render_target_sized_origin(output, None)?;
            self.chain.frame(&self.input, &viewport, &mut cmd, frame_count, None)?;
            if keep {
                cmd.copy_texture_to_buffer(
                    self.target.as_image_copy(),
                    wgpu::TexelCopyBufferInfo {
                        buffer: &self.readbacks[slot].buffer,
                        layout: wgpu::TexelCopyBufferLayout {
                            offset: 0,
                            bytes_per_row: Some(self.padded_row),
                            rows_per_image: None,
                        },
                    },
                    self.target.size(),
                );
            }
            let index = self.queue.submit([cmd.finish()]);
            if keep {
                let state = Arc::clone(&self.readbacks[slot].state);
                state.store(1, Ordering::Release);
                self.readbacks[slot].buffer.map_async(wgpu::MapMode::Read, .., move |r| {
                    state.store(if r.is_ok() { 2 } else { 3 }, Ordering::Release)
                });
            }
            let prev = self.pending.replace((index, slot, keep));
            match prev {
                Some((index, prev_slot, true)) => {
                    self.collect(index, prev_slot, out)?;
                    Ok(true)
                }
                _ => Ok(false),
            }
        }

        fn finish(&mut self, out: &mut [u8]) -> Result<bool> {
            match self.pending.take() {
                Some((index, slot, true)) => {
                    self.collect(index, slot, out)?;
                    Ok(true)
                }
                Some((index, _, false)) => {
                    self.device.poll(wgpu::PollType::Wait { submission_index: Some(index), timeout: None })?;
                    Ok(false)
                }
                None => Ok(false),
            }
        }
    }
}

fn make_drawer(a: &Args) -> Result<Box<dyn Drawer>> {
    match a.runtime.as_str() {
        #[cfg(target_vendor = "apple")]
        "metal" => Ok(Box::new(metal::Metal::new(a)?)),
        "wgpu" => Ok(Box::new(wgpu_runtime::Wgpu::new(a)?)),
        other => {
            let have = if cfg!(target_vendor = "apple") { "metal, wgpu" } else { "wgpu" };
            bail!("no {other} runtime in this crt-stream (it has {have})")
        }
    }
}

/// Fills `buf` from `r`; false at the end of the stream before the first byte.
fn read_frame(r: &mut impl Read, buf: &mut [u8]) -> Result<bool> {
    let mut got = 0;
    while got < buf.len() {
        match r.read(&mut buf[got..]) {
            Ok(0) if got == 0 => return Ok(false),
            Ok(0) => bail!("the input stopped in the middle of a frame ({got} of {} bytes)", buf.len()),
            Ok(n) => got += n,
            Err(e) if e.kind() == ErrorKind::Interrupted => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(true)
}

fn report(line: &str) {
    let mut err = std::io::stderr().lock();
    let _ = writeln!(err, "{line}");
    let _ = err.flush();
}

fn run(a: Args) -> Result<()> {
    let t0 = Instant::now();
    let mut drawer = make_drawer(&a)?;
    report(&format!("CRT_READY {}; {:.2}", drawer.describe(), t0.elapsed().as_secs_f64()));

    let in_bytes = a.input.0 as usize * a.input.1 as usize * 4;
    let out_bytes = a.output.0 as usize * a.output.1 as usize * 4;
    // The frames read back go out from a second thread, so the encoder's pace overlaps with the drawing
    let (to_writer, writer_rx) = mpsc::sync_channel::<Vec<u8>>(2);
    let (free_tx, free_rx) = mpsc::channel::<Vec<u8>>();
    let writer = std::thread::spawn(move || -> std::io::Result<()> {
        let mut stdout = std::io::stdout().lock();
        for frame in writer_rx {
            stdout.write_all(&frame)?;
            let _ = free_tx.send(frame);
        }
        stdout.flush()
    });
    let spare = || free_rx.try_recv().unwrap_or_else(|_| vec![0u8; out_bytes]);
    let mut stdin = std::io::stdin().lock();
    let mut frame = vec![0u8; in_bytes];
    let mut out = spare();
    let mut written = 0usize;
    let mut send = |out: &mut Vec<u8>, fresh: Vec<u8>| -> Result<()> {
        let full = std::mem::replace(out, fresh);
        to_writer.send(full).map_err(|_| anyhow!("couldn't write frame {written}: the output closed"))?;
        written += 1;
        report(&format!("CRT_FRAMES {written}"));
        Ok(())
    };

    let result = (|| -> Result<()> {
        if !read_frame(&mut stdin, &mut frame)? {
            return Ok(());
        }
        for step in 0..a.warmup {
            drawer.draw(&frame, step, false, &mut out)?;
        }
        let mut count = a.warmup;
        loop {
            if drawer.draw(&frame, count, true, &mut out)? {
                send(&mut out, spare())?;
            }
            count += 1;
            if !read_frame(&mut stdin, &mut frame)? {
                break;
            }
        }
        if drawer.finish(&mut out)? {
            send(&mut out, spare())?;
        }
        Ok(())
    })();
    drop(send);
    drop(to_writer);
    let wrote = writer.join().map_err(|_| anyhow!("the writer thread panicked"))?;
    result?;
    wrote.map_err(|e| anyhow!("couldn't write the frames: {e}"))?;
    report(&format!("CRT_DONE {written} {:.1}", t0.elapsed().as_secs_f64()));
    Ok(())
}

fn main() {
    let result = parse_args().and_then(run);
    if let Err(e) = result {
        report(&format!("crt-stream: {e:#}"));
        std::process::exit(1);
    }
}
