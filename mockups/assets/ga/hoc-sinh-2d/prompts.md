# hoc-sinh-2d test (FLUX.2 klein 4B, @cf/black-forest-labs/flux-2-klein-4b, 768x1024, multipart API)

## nam-daihoc.png  (text-to-image, seed 11)
```
Polished Gunny-style Vietnamese mobile game 2D hand-painted chibi anime character sprite, full body, front three-quarter view, standing confidently, one hand in jeans pocket, other arm relaxed. Cute super-deformed chibi proportions, oversized head about 1:2.3 of body height. A 19-year-old Vietnamese university student boy with big sculpted swept-back spiky quiff hair, dark brown with caramel-blonde tips, voluminous, strong cel-shaded highlights on hair. Large expressive anime eyes, friendly confident open smile. Teal bomber jacket with a small plain orange rectangular patch on the chest with no letters or text, white t-shirt, light-wash blue jeans, white sneakers with orange accents, slim grey laptop backpack, black headphones around the neck. Clean dark outline, saturated colours, painted cel shading. Perfectly flat uniform solid pure magenta background #FF00FF with no gradient, no floor, no cast shadow under the feet, no text anywhere, full body visible head to feet.
```

## nam-daihoc-ben.png  (reference = the raw e1 image as input_image_0, seed 11)
```
Draw this exact same character again, same face, same hairstyle (dark brown swept spiky quiff with caramel tips), same teal bomber jacket with orange patch, white tee, light-wash jeans, white sneakers with orange accents, grey laptop backpack and black headphones, same 2D hand-painted chibi anime style and proportions. New pose: side three-quarter view facing right, walking forward mid-stride, one hand in the jeans pocket, friendly smile. Perfectly flat uniform solid pure magenta background #FF00FF, no floor, no cast shadow, no text, full body visible head to feet.
```

Other explored (not used): seeds 11/22/33 with earlier prompts, seeds 12/13 of the chosen prompt, seed 21 of the side prompt. 13 calls total.
Matte: flood-fill magenta keyed from the border (g < 0.55*min(r,b)), largest blob, 1px erode + 0.9px blur, magenta despill on edges; framed 512px, height 80%, feet at 95%.
