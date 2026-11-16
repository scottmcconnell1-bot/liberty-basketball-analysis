# Board templates

Built by `build_templates.py --videos-dir PATH` from `.team/design48b/` labels
and `train48_meta.json`. Board box from `game_session.find_board`.

npz keys:
- `X` float32 (N, 240) digit vectors
- `y` str (N,) digit labels
- `ref` float32 (72, 128) reference board image
- `max_dist` float scalar

sha256 (filled by build_templates.py):
- home.npz: `3b92f5dcd2777d3ef45e89bde2d248e986a3c9fd35f9b0eb939074016a5094a5`
- away_adrian.npz: `caa7ffc75c9ccc039ea1cbbb0f2814f70d423392f2b61ab4e194c7921f48830d`
