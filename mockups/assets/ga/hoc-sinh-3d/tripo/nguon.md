# Tripo API test (2026-11-23) - BLOCKED: account balance 0

Result: balance {balance: 0.0, frozen: 0.0}; POST /generation/image-to-model returned HTTP 403 code 2010
"You don't have enough credit to create this task". No model, rig or animation was produced; 0 credits used.
Script tripo3d.py (../../src) is written but only `balance` and the upload (/files) are verified against the live API.

Docs: https://developers.tripo3d.ai (old platform.tripo3d.ai/docs redirects there). Base https://openapi.tripo3d.ai/v3, Bearer auth.
- POST /files (multipart field `file`, PNG/JPEG <=20MB) -> data.file_token
- POST /generation/image-to-model {input, model: v3.1-20260211|P1-20260311|P2-20260801, texture, pbr, texture_quality,
  texture_alignment, orientation(align_image), face_limit, quad, smart_low_poly, ...}; no cartoon "style" parameter exists
- GET /tasks/{id} -> status success|failed|cancelled|banned|expired, output.model_url (expires, download at once)
- POST /animations/rig-check {input: task_id} -> output.riggable, rig_type
- POST /animations/rig {input, model: v3.0-20260909, rig_type: biped, spec: tripo, out_format: glb}
- POST /animations/retarget {input: rig task_id, animation(s): preset:idle, preset:walk, preset:run ... (v3.0 biped, 11 presets)}
- GET /account/balance -> data.balance, data.frozen
Credits: docs give no price table; only sample results (rig 25, retarget 10, text_to_model 100). "1 credit = $0.01" from Dec 1 2026;
failed/cancelled tasks are not charged. Real cost via GET /v3/account/usage.
Terms (https://developers.tripo3d.ai/en/terms): "Section 5.2.1 Users Free of Charge" (Tripo retains rights to Inputs/Outputs),
"Section 5.2.2 Paid Users" (paid users generally have all rights), "Section 3.2" (lawful commercial use of Outputs allowed, no guarantee of exclusivity),
"Section 6.4 Refund Policy" (API credits non-refundable). Free-tier outputs are therefore not ours; need paid credits for the game.
