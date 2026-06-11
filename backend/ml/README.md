# Experimental plan detector

The normal TimberBIM Lite server does not require ML packages. Install
`backend/requirements-ml.txt`, set `KERAS_BACKEND`, and point
`TIMBERBIM_PLAN_MODEL` at reviewed Keras 3 detector weights to activate the
adapter.

Suggested training data:

```text
dataset/
  images/
    sheet-001.png
  annotations.csv
  classes.txt
```

`annotations.csv` columns:

```text
image_file,class_name,x_min,y_min,x_max,y_max,level,notes
```

Classes are `exterior_wall`, `interior_wall`, `door_opening`,
`window_opening`, `garage_opening`, `truss_line`, `dimension_text`,
`grid_line`, and `ignore`.

Use `train_plan_detector.py` only as an experimental starting point. A useful
system needs licensed, representative drawings; separate train/validation/test
sets; scale and rotation augmentation; detection/segmentation metrics; and
human review. It is not construction-grade and must never auto-commit geometry.
