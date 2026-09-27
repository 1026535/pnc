# Accepted World-map detector

The current detector is corrected-label v25, new epoch 3 (`epoch2.pt`), accepted
by the user on September 26, 2026 for current map use. The checkpoint SHA-256 is
`071b18f639f94ca3a73acc0f7c2ebb9a9af347aaad9d4196b8b6dea5e514a45d`.
The exported ONNX identity and class order are pinned by
`pnc_automation/app/pnc/vision/world_yolo_qualification.py`.

Configure the local export in `config/accounts.yaml`:

```yaml
runtime:
  world_yolo_model_path: .local-data/models/world_yolo/v25-corrected-epoch3.onnx
```

Paths resolve from the config's workspace, as artifact paths do. The application
loads and validates the configured model once and shares it across both
observation pipelines. An explicit injected producer takes precedence. Omission
keeps YOLO disabled; an invalid configured model fails rather than falling back.
Inference runs only for an explicit World YOLO observation request.

The central ROI, confidence threshold 0.35 and Castle observation publication
scope remain in force. Other classes remain diagnostic. This model selection
does not qualify new classes or carry forward another model's tap policy.

The acceptance is an explicit user exception: one validation lumber camp drops
below threshold (19 to 18 correct detections). The original frozen gate still
fails; the run's historical selection record is preserved. The corrected dataset
contains 669 training images, 7,059 boxes and 17 classes. Sparse and correlated
validation support and benchmark reuse limit conclusions about generalization.

Local evidence is under the training worktree's
`.local-data/yolo_evaluation_v25/gold_mine_training_20260922/`:
`REVIEWED_REPORT.md` preserves the training review; `user_acceptance_20260926/`
contains the separate acceptance, unchanged test35 audit, export parity,
actual-adapter replay and paired CPU timing. Runtime binaries remain local and
are not committed.
