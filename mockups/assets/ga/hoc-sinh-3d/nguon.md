# hoc-sinh-3d: nguon (2026-11-23)
Input: ../hoc-sinh-2d/nam-daihoc.png (512 px RGBA, truyen thang RGBA, khong ghep nen).

## sf3d.glb
- Space: Upsampler/stable-fast-3d (ban sao cua stabilityai/stable-fast-3d; ban chinh thuc tra loi "upstream exception" 2 lan ~4 s moi lan)
- Endpoint /image_to_glb: foreground_ratio=0.85, remesh_option="None", vertex_count=-1, texture_size=1024
- Thoi gian: 16 s, 1 lan. Ra GLB co texture (10.9k dinh, 15.7k mat), 833 KB.
- Model licence (model card stabilityai/stable-fast-3d): Stability AI Community License

## triposr.glb
- Space: Pheerakarn/TripoSR (ban sao cua stabilityai/TripoSR; ban chinh thuc o trang thai RUNTIME_ERROR)
- Endpoints: /preprocess (remove_background=False, foreground_ratio=0.85) roi /generate (marching_cubes_resolution=256)
- Thoi gian: 76 s tong, 1 lan. Ra GLB mau dinh (27.6k dinh, 55k mat), 1.1 MB. Truc Y/Z lech: can xoay 90 do quanh X khi import.
- Model licence (model card stabilityai/TripoSR): MIT

Render: Blender 4.5 headless, cel-shading + inverted-hull outline; sf3d xoay yaw 180 de quay mat ve camera, triposr RX 90, gamma mau 2.2.
