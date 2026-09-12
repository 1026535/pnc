# YOLO vision-layer prototype

Branch: `codex/yolo-unspecialized-eval`, continued from `codex/yolo-vision-prototype`. The existing dirty YOLO worktree and its unrelated replacement-core changes were preserved; they were not committed, reverted, or reformatted as part of this evaluation.

## What is pretrained?

YOLO is a model family. The standard YOLO26 detection weights are pretrained on COCO's 80 everyday-object classes. They have useful learned visual features, but no PNC class vocabulary. A detection labelled `person` does not establish a monster, lord, castle, or actionable game control. For those classes, start with pretrained weights and fine-tune using reviewed PNC bounding boxes. No PNC training was performed in this task. Sources: [YOLO26 model documentation](https://docs.ultralytics.com/models/yolo26), [fine-tuning guide](https://docs.ultralytics.com/guides/finetuning-guide).

## Implemented boundary

- `core/vision/detection/yolo_onnx.py`: local CPU ONNX inference, typed pixel-space boxes, validated YOLO26 end-to-end output contract, letterboxing and coordinate inversion. No runtime downloads or PyTorch requirement. Other YOLO export layouts fail explicitly.
- `app/pnc/vision/yolo_shadow.py`: consumes the same `CapturedScreenshot` and canonical `Observation`, checks frame identity, and returns diagnostic detections separately. Explicit custom labels can be mapped to existing `DetectedSpatialObject` candidates only on an unobstructed recognized spatial surface. These candidates never replace the authoritative observation or feed an action executor.
- `tools/prototype_yolo.py`: saved-image, reviewed-manifest, and bounded live probes with local JSON reports, labelled previews, model/frame hashes, split summaries, and inference timing. Live mode holds one canonical account reservation across instance resolution, PNC foregrounding, startup observation, every live capture and inference, per-frame evidence persistence, and connected-runtime cleanup. It disables roster persistence and performs no navigation or game action.
- `config/yolo_classes.example.json`: an example for a future model trained with those exact PNC labels. It deliberately fails against COCO weights. No automatic COCO-to-PNC relabelling is supplied.

This is an opt-in shadow prototype; normal automation does not load YOLO. The existing screen, popup, OCR, navigation and action paths are preserved. Raw detections may be displayed on unsupported or blocked frames for diagnosis; they cannot become eligible spatial candidates there. The world-map coordinate-only fast path is unchanged.

## Reproduce inference

The runtime extra is `yolo` (`onnxruntime`). It was already installed on the development machine as version 1.24.3. On another environment, install the project with `py -m pip install -e ".[yolo]"`.

The tested local model is an Ultralytics-compatible COCO YOLO26n ONNX export supplied by **community publisher prithivMLmods**, not downloaded from an official Ultralytics ONNX release. Its metadata reports Ultralytics 8.4.100, task `detect`, `end2end=True`, input `[1,3,640,640]`, output `[1,300,6]` (xyxy, score, class ID). The model metadata identifies AGPL-3.0; see the publisher/model licensing before distribution. ONNX inference does not remove model licensing terms.

- Publisher: [pinned model repository](https://huggingface.co/prithivMLmods/YOLO26-ONNX/tree/c526dae7a5a5b4f1d79d704903b4406011da2716)
- File: `yolo26n/yolo26n.onnx`
- SHA-256: `00e2d1062178fca312fee35cf5fc9b9c783b3e5c9675d48b84929f69ee391807`
- Local path: `artifacts/yolo_prototype/models/yolo26n-standard.onnx` (ignored generated asset).

To fetch exactly that model:

```powershell
New-Item -ItemType Directory -Force artifacts/yolo_prototype/models | Out-Null
Invoke-WebRequest -Uri 'https://huggingface.co/prithivMLmods/YOLO26-ONNX/resolve/c526dae7a5a5b4f1d79d704903b4406011da2716/yolo26n/yolo26n.onnx' -OutFile artifacts/yolo_prototype/models/yolo26n-standard.onnx
Get-FileHash artifacts/yolo_prototype/models/yolo26n-standard.onnx -Algorithm SHA256
```

Verify the hash against the value above, then run:

```powershell
py tools/prototype_yolo.py --model artifacts/yolo_prototype/models/yolo26n-standard.onnx --image tests/data/screen_recognition/hero_hall.png --image tests/data/screen_recognition/home_negative.png
py tools/prototype_yolo.py --model artifacts/yolo_prototype/models/yolo26n-standard.onnx --manifest tests/data/screen_recognition/manifest.json
py tools/prototype_yolo.py --model artifacts/yolo_prototype/models/yolo26n-standard.onnx --live --account 3xx_spies --live-samples 3
```

`--image` can repeat. Each invocation creates a unique directory under `artifacts/yolo_prototype/runs`. Loading an explicit local file is required; inference never silently fetches weights. Live mode waits up to 90 seconds for a visually populated PNC frame and prefers a known non-loading screen. If recognition remains `UNKNOWN`, it retains the latest visually populated frame as a diagnostic fallback and never acts on it. Model load time and existing OCR/capture latency are outside the reported detector time. Timing is an execution measurement, not a controlled comparison or accuracy estimate.

## Path to useful PNC detections

Choose a small target set such as monsters, resource nodes, and castles. Label their bounding boxes on diverse screenshots, including empty terrain, HUD, popups and confusing artwork as negatives. Split by session/day/account rather than adjacent frames. Keep levels, coordinates, timers and names as OCR content, not separate detector classes. The current 29 screen-recognition frames do not constitute an annotated object-detection dataset.

In a separate training environment with Ultralytics installed, a starting workflow is:

```python
from ultralytics import YOLO

model = YOLO("yolo26n.pt")
model.train(data="path/to/reviewed_pnc_dataset.yaml", epochs=50, imgsz=640)
trained = YOLO("path/to/run/weights/best.pt")
trained.export(format="onnx", imgsz=640, batch=1, dynamic=False, nms=False)
```

This is illustrative training setup, not a completed training run or a guaranteed sufficient epoch count. The exported model must meet the adapter's validated end-to-end metadata and output contract. See [ONNX export](https://docs.ultralytics.com/integrations/onnx) and [detection annotation format](https://docs.ultralytics.com/datasets/detect).

After training, use `--class-map config/yolo_classes.example.json` only if the model contains those exact labels. Evaluate held-out precision, recall, localization, popup/HUD false positives, latency and unknown handling before any promotion into actionable observations. Keep shadow candidates separate until this evidence supports a specific task.

## Validation

- `py -m unittest tests.test_yolo_onnx tests.test_yolo_shadow tests.test_prototype_yolo tests.test_benchmark_screen_recognition`: passed 21 tests. They cover letterbox inversion, padding/clipping, malformed models/labels/outputs, reversed boxes, class filtering, exact-frame matching, mapping validation, popup/unknown suppression, no authoritative observation mutation, aggregate assessment, launch-transition rejection, and bounded visual-state fallback.
- Current-vision comparison: `py tools/benchmark_screen_recognition.py --manifest tests/data/screen_recognition/manifest.json --output artifacts/yolo_manifest_eval/current_vision_benchmark.json` evaluated all 29 reviewed frames. It returned nonzero because two reference frames were classified as generic `pnc_popup` instead of `pnc_world_coordinate_dialog` and `pnc_research_queue`; holdout and validation had zero wrong actionable classifications. YOLO did not repair or alter either result.
- Generic YOLO manifest evaluation at confidence 0.20 produced 29 boxes on 12 of 29 frames: `person=16`, `sports ball=7`, `tv=2`, and one each of `cell phone`, `kite`, `laptop`, and `traffic light`. At confidence 0.35 it produced 12 boxes on six frames: `person=8`, `sports ball=3`, and `traffic light=1`. Both thresholds produced zero PNC candidates and changed zero authoritative observations. At 0.35, the holdout split had no retained detections. Evidence: `artifacts/yolo_manifest_eval/20260912T040959Z_0c847399/summary.json` and `artifacts/yolo_manifest_eval/20260912T041615Z_cd8d8e29/summary.json`.
- The corrected live probe reserved `3xx_spies` for its complete runtime scope and evaluated three fresh frames at confidence 0.35. Startup readiness reached a known `pnc_popup` frame on the first observation. The stock model produced six `person` boxes on illustrated characters, while the blocking-popup gate produced zero PNC candidates and the authoritative observation remained unchanged. Detector median was about 106 ms and p95 about 132 ms. Evidence: `artifacts/yolo_live_eval/20260912T042646Z_1f15655d/summary.json` and its previews. No castle switch, navigation, tap, or resource spending occurred.
- An earlier live attempt captured three visually blank frames immediately after foregrounding PNC. That run exposed the missing startup-readiness wait; the new bounded visual predicate and tests address it. Evidence: `artifacts/yolo_live_eval/20260912T042350Z_c8b75cae/summary.json`.
- Saved inference: `py tools/prototype_yolo.py --model artifacts/yolo_prototype/models/yolo26n-standard.onnx --image tests/data/screen_recognition/hero_hall.png --image tests/data/screen_recognition/home_negative.png --image artifacts/2026-06-15/serious_stuff/20260615T210317Z_live_default_stride6_preflight_step_0_post_action_1.png --image tests/data/screen_recognition/alliance_invitation.png` passed on four frames. Evidence: `artifacts/yolo_prototype/runs/20260910T221217Z_b26739d9/summary.json` and corresponding previews.
- At confidence 0.35: Hero Hall and Home had no retained boxes; the archived world map had one `person` box on the HUD player portrait; the alliance invitation had two `person` boxes. None became PNC candidates. Measured detector times were approximately 314–695 ms while other OCR work was running; this is not a controlled latency benchmark.
- `py tools/prototype_yolo.py --model artifacts/yolo_prototype/models/yolo26n-standard.onnx --live --account testing`: passed local inference on a fresh 900×1600 capture through the configured runtime. Evidence: `artifacts/yolo_prototype/runs/20260910T221233Z_2e18fd61/summary.json`. The image visibly shows the world map with collapsed HUD, a level-10 territory, Treant, Venom Spider and Hell Fortress. Canonical recognition returned UNKNOWN, which was preserved; YOLO retained no boxes above 0.35. This proves capture/inference integration and conservative handling, not live PNC detection accuracy or active-castle identity verification. No navigation, castle switch, or resource spending occurred. The tool ensures PNC is foregrounded but does not record whether BlueStacks itself was already running versus launched by the resolver.
- `py -m unittest discover -s tests`: passed 1,199 tests with 22 skips and zero failures or errors (52.567 seconds) on the committed code state.
- `git diff --check`: passed.

The concrete result is a functioning detector adapter and safe shadow-evaluation boundary. The expanded offline and live evidence finds no measured PNC vision improvement from unspecialized COCO weights. A custom PNC model and reviewed bounding-box dataset are required before another promotion decision; the prototype does not silently promote generic detections or claim the remaining recognition work is finished.
