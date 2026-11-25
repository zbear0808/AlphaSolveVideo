# Name tags

Players who picked a name tag at the character select screen have it drawn above their fighter. A render draws it whenever it draws the HUD, and it can say something else, or nothing:

```sh
python3 -m slp2alpha info game.slp                                     # ... name tags P1 'DUFF', P4 'BOZO'
python3 -m slp2alpha render game.slp --nametag P1=Zubair --nametag P4=  # P1's tag says Zubair, P4's is hidden
python3 -m slp2alpha render game.slp --no-nametags                     # no tags, the rest of the HUD as usual
python3 tools/slp2video/slp2video.py game.slp --nametag "P1=Mr. Fox"   # the same options in slp2video
```

The output's name says so: `game (name tags changed)`, `game (no name tags)`.

## When they're drawn

Melee draws the tags with the HUD and hides them with it:

| Render | Name tags |
|---|---|
| default (the stage without its background, transparent) | drawn, into the transparent video, with their box and arrow |
| `--keep-background` | drawn |
| `--characters-only`, `--model` | hidden, with the HUD; `--hud` draws both |
| `--no-hud` | hidden |

`--nametag` with the HUD hidden prints a note, since nothing would change.

## What a tag can say

- **Length.** The tag holds 8 bytes. Letters (upper and lower case), digits, spaces and `. , ' -` take one each, so up to 8 of them: `ZUBAIR77`. Other symbols and kana take two.
- **Characters.** The ones Melee's font was seen to draw: letters, digits, the ASCII symbols except `` ` ``, `"` and `\` (drawn blank), hiragana and katakana. Kanji and the separate voicing marks (`゛`) are refused: they're drawn blank or broken. A full-width letter you type (`Ｄ`) is the plain one.
- **The box** widens to fit, through Slippi's Extended Nametag Box code.
- **Only a tag the replay shows** can be changed. A player without one has no tag slot for the game to draw from; `--nametag P2=...` then skips the replay and says which players have tags. Replays before Slippi v1.3.0 don't hold the tags' text, and show none.

## How it works

The replay's Game Start event holds each player's tag: its slot in the game info block, and from v1.3.0 the 16 bytes of the slot from its 8-byte name on (`0x161`, `0x10` apart). Slippi's playback (`Playback/Core/RestoreGameInfo.asm`) copies them back into the slot before the match, and Melee's tag code draws the slot's name. A first byte of 0 makes the playback code give the player no tag.

So `render` writes a copy of the replay in its work folder with the new text and plays that; the replay itself isn't touched. The text goes into the 8-byte name, with its terminator after it. The bytes past the name are the slot's other settings (rumble, handicap) and the next slot's data, and stay as they were recorded. A tag of 8 bytes ends where the name does: the byte after it is 0 in Melee's own slots too.

Checked on Battlefield (`DishonestMuddyCoyote.slp`, which has the tags DUFF and BOZO):

- the new text is drawn and the box fits it; an empty tag hides it, with the HUD kept;
- the game plays the same: 600 frames with both tags changed came out bit-identical to the same render without the change, except for one frame early in the clip. Two renders with no change differ the same way, on one frame of their own.
