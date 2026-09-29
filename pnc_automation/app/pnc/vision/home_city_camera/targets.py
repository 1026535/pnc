"""Measured Home-city target merge and publisher surface helpers."""

from __future__ import annotations

from dataclasses import replace

from pnc_automation.app.pnc.domain.building_catalog import home_city_object_id_from_metadata
from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject

def merge_camera_target_objects(
    objects: tuple[DetectedSpatialObject, ...],
    camera_objects: tuple[DetectedSpatialObject, ...],
) -> tuple[DetectedSpatialObject, ...]:
    """Prefer measured bodies and attach only mutually unambiguous label facts.

    All measured instances survive. Once a semantic type has measured body
    evidence, its OCR-only duplicates cannot remain selectable objects. A
    label enriches a body only if each has exactly one compatible counterpart;
    counting both sides before merging prevents order-dependent level claims.
    """

    if not camera_objects:
        return objects
    object_ids = tuple(home_city_object_id_from_metadata(item.metadata) for item in objects)
    camera_ids = tuple(home_city_object_id_from_metadata(item.metadata) for item in camera_objects)
    measured_ids = {object_id for object_id in camera_ids if object_id is not None}
    compatible_bodies: list[list[int]] = [[] for _ in objects]
    compatible_labels: list[list[int]] = [[] for _ in camera_objects]
    for label_index, (label, object_id) in enumerate(zip(objects, object_ids)):
        if object_id not in measured_ids:
            continue
        for body_index, (body, camera_id) in enumerate(zip(camera_objects, camera_ids)):
            if camera_id != object_id:
                continue
            if (
                label.home_city_slot is not None
                and body.home_city_slot is not None
                and label.home_city_slot != body.home_city_slot
            ):
                continue
            compatible_bodies[label_index].append(body_index)
            compatible_labels[body_index].append(label_index)

    merged = [
        item for item, object_id in zip(objects, object_ids)
        if object_id not in measured_ids
    ]
    for body_index, body in enumerate(camera_objects):
        labels = compatible_labels[body_index]
        if len(labels) == 1 and len(compatible_bodies[labels[0]]) == 1:
            label = objects[labels[0]]
            body = replace(
                body,
                name_text=label.name_text or body.name_text,
                level=label.level if label.level is not None else body.level,
                metadata={
                    **body.metadata,
                    **{key: value for key, value in label.metadata.items() if key == "home_city_label"},
                },
            )
        merged.append(body)
    return tuple(merged)
