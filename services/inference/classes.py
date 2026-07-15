"""
YOLOX / COCO-80 class definitions and semantic group mappings.

All 80 COCO classes are divided into 10 human-readable groups that
drive alert-rule filtering and Grafana dashboard labels.

License note: The COCO class list itself is factual data (not code)
and is in the public domain. The groupings are original to this project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── Group enum ────────────────────────────────────────────

class ClassGroup(str, Enum):
    PEOPLE             = "people"
    VEHICLES           = "vehicles"
    TRAFFIC_INFRA      = "traffic_infrastructure"
    ANIMALS            = "animals"
    PERSONAL_ITEMS     = "personal_items"
    SPORTS_RECREATION  = "sports_recreation"
    FOOD_DRINK         = "food_drink"
    FURNITURE_HOUSEHOLD = "furniture_household"
    ELECTRONICS        = "electronics"
    EVERYDAY_OBJECTS   = "everyday_objects"


# ── Class descriptor ─────────────────────────────────────

@dataclass(frozen=True)
class CocoClass:
    index:      int
    name:       str
    group:      ClassGroup
    # Relevant for CCTV security use-cases (drives default alert rule suggestions)
    security_relevant: bool = False


# ── Full 80-class registry ────────────────────────────────
# Order matches YOLOX output indices (identical to COCO class ordering).

COCO_CLASSES: list[CocoClass] = [
    # ── People ───────────────────────────────────────────
    CocoClass(0,  "person",          ClassGroup.PEOPLE,            security_relevant=True),

    # ── Vehicles ─────────────────────────────────────────
    CocoClass(1,  "bicycle",         ClassGroup.VEHICLES,          security_relevant=True),
    CocoClass(2,  "car",             ClassGroup.VEHICLES,          security_relevant=True),
    CocoClass(3,  "motorcycle",      ClassGroup.VEHICLES,          security_relevant=True),
    CocoClass(4,  "airplane",        ClassGroup.VEHICLES),
    CocoClass(5,  "bus",             ClassGroup.VEHICLES,          security_relevant=True),
    CocoClass(6,  "train",           ClassGroup.VEHICLES),
    CocoClass(7,  "truck",           ClassGroup.VEHICLES,          security_relevant=True),
    CocoClass(8,  "boat",            ClassGroup.VEHICLES),

    # ── Traffic Infrastructure ────────────────────────────
    CocoClass(9,  "traffic light",   ClassGroup.TRAFFIC_INFRA),
    CocoClass(10, "fire hydrant",    ClassGroup.TRAFFIC_INFRA),
    CocoClass(11, "stop sign",       ClassGroup.TRAFFIC_INFRA),
    CocoClass(12, "parking meter",   ClassGroup.TRAFFIC_INFRA),
    CocoClass(13, "bench",           ClassGroup.TRAFFIC_INFRA),

    # ── Animals ───────────────────────────────────────────
    CocoClass(14, "bird",            ClassGroup.ANIMALS),
    CocoClass(15, "cat",             ClassGroup.ANIMALS),
    CocoClass(16, "dog",             ClassGroup.ANIMALS),
    CocoClass(17, "horse",           ClassGroup.ANIMALS),
    CocoClass(18, "sheep",           ClassGroup.ANIMALS),
    CocoClass(19, "cow",             ClassGroup.ANIMALS),
    CocoClass(20, "elephant",        ClassGroup.ANIMALS),
    CocoClass(21, "bear",            ClassGroup.ANIMALS,           security_relevant=True),
    CocoClass(22, "zebra",           ClassGroup.ANIMALS),
    CocoClass(23, "giraffe",         ClassGroup.ANIMALS),

    # ── Personal Items ────────────────────────────────────
    CocoClass(24, "backpack",        ClassGroup.PERSONAL_ITEMS),
    CocoClass(25, "umbrella",        ClassGroup.PERSONAL_ITEMS),
    CocoClass(26, "handbag",         ClassGroup.PERSONAL_ITEMS),
    CocoClass(27, "tie",             ClassGroup.PERSONAL_ITEMS),
    CocoClass(28, "suitcase",        ClassGroup.PERSONAL_ITEMS,    security_relevant=True),

    # ── Sports & Recreation ───────────────────────────────
    CocoClass(29, "frisbee",         ClassGroup.SPORTS_RECREATION),
    CocoClass(30, "skis",            ClassGroup.SPORTS_RECREATION),
    CocoClass(31, "snowboard",       ClassGroup.SPORTS_RECREATION),
    CocoClass(32, "sports ball",     ClassGroup.SPORTS_RECREATION),
    CocoClass(33, "kite",            ClassGroup.SPORTS_RECREATION),
    CocoClass(34, "baseball bat",    ClassGroup.SPORTS_RECREATION, security_relevant=True),
    CocoClass(35, "baseball glove",  ClassGroup.SPORTS_RECREATION),
    CocoClass(36, "skateboard",      ClassGroup.SPORTS_RECREATION),
    CocoClass(37, "surfboard",       ClassGroup.SPORTS_RECREATION),
    CocoClass(38, "tennis racket",   ClassGroup.SPORTS_RECREATION),

    # ── Food & Drink ──────────────────────────────────────
    CocoClass(39, "bottle",          ClassGroup.FOOD_DRINK),
    CocoClass(40, "wine glass",      ClassGroup.FOOD_DRINK),
    CocoClass(41, "cup",             ClassGroup.FOOD_DRINK),
    CocoClass(42, "fork",            ClassGroup.FOOD_DRINK),
    CocoClass(43, "knife",           ClassGroup.FOOD_DRINK,        security_relevant=True),
    CocoClass(44, "spoon",           ClassGroup.FOOD_DRINK),
    CocoClass(45, "bowl",            ClassGroup.FOOD_DRINK),
    CocoClass(46, "banana",          ClassGroup.FOOD_DRINK),
    CocoClass(47, "apple",           ClassGroup.FOOD_DRINK),
    CocoClass(48, "sandwich",        ClassGroup.FOOD_DRINK),
    CocoClass(49, "orange",          ClassGroup.FOOD_DRINK),
    CocoClass(50, "broccoli",        ClassGroup.FOOD_DRINK),
    CocoClass(51, "carrot",          ClassGroup.FOOD_DRINK),
    CocoClass(52, "hot dog",         ClassGroup.FOOD_DRINK),
    CocoClass(53, "pizza",           ClassGroup.FOOD_DRINK),
    CocoClass(54, "donut",           ClassGroup.FOOD_DRINK),
    CocoClass(55, "cake",            ClassGroup.FOOD_DRINK),

    # ── Furniture & Household ─────────────────────────────
    CocoClass(56, "chair",           ClassGroup.FURNITURE_HOUSEHOLD),
    CocoClass(57, "couch",           ClassGroup.FURNITURE_HOUSEHOLD),
    CocoClass(58, "potted plant",    ClassGroup.FURNITURE_HOUSEHOLD),
    CocoClass(59, "bed",             ClassGroup.FURNITURE_HOUSEHOLD),
    CocoClass(60, "dining table",    ClassGroup.FURNITURE_HOUSEHOLD),
    CocoClass(61, "toilet",          ClassGroup.FURNITURE_HOUSEHOLD),

    # ── Electronics ───────────────────────────────────────
    CocoClass(62, "tv",              ClassGroup.ELECTRONICS,       security_relevant=True),
    CocoClass(63, "laptop",          ClassGroup.ELECTRONICS,       security_relevant=True),
    CocoClass(64, "mouse",           ClassGroup.ELECTRONICS),
    CocoClass(65, "remote",          ClassGroup.ELECTRONICS),
    CocoClass(66, "keyboard",        ClassGroup.ELECTRONICS),
    CocoClass(67, "cell phone",      ClassGroup.ELECTRONICS),
    CocoClass(68, "microwave",       ClassGroup.ELECTRONICS),
    CocoClass(69, "oven",            ClassGroup.ELECTRONICS),
    CocoClass(70, "toaster",         ClassGroup.ELECTRONICS),
    CocoClass(71, "sink",            ClassGroup.ELECTRONICS),
    CocoClass(72, "refrigerator",    ClassGroup.ELECTRONICS),

    # ── Everyday Objects ──────────────────────────────────
    CocoClass(73, "book",            ClassGroup.EVERYDAY_OBJECTS),
    CocoClass(74, "clock",           ClassGroup.EVERYDAY_OBJECTS),
    CocoClass(75, "vase",            ClassGroup.EVERYDAY_OBJECTS),
    CocoClass(76, "scissors",        ClassGroup.EVERYDAY_OBJECTS),
    CocoClass(77, "teddy bear",      ClassGroup.EVERYDAY_OBJECTS),
    CocoClass(78, "hair drier",      ClassGroup.EVERYDAY_OBJECTS),
    CocoClass(79, "toothbrush",      ClassGroup.EVERYDAY_OBJECTS),
]

# ── Fast lookup tables ────────────────────────────────────

# index → CocoClass (used during inference: YOLOX gives you an int class id)
BY_INDEX: dict[int, CocoClass] = {c.index: c for c in COCO_CLASSES}

# name → CocoClass (used in alert rule evaluation)
BY_NAME: dict[str, CocoClass] = {c.name: c for c in COCO_CLASSES}

# group → [CocoClass] (used in Grafana label generation + API filters)
BY_GROUP: dict[ClassGroup, list[CocoClass]] = {}
for _cls in COCO_CLASSES:
    BY_GROUP.setdefault(_cls.group, []).append(_cls)

# Flat list of names in index order — passed directly to YOLOX postprocess
CLASS_NAMES: list[str] = [c.name for c in COCO_CLASSES]

# Security-relevant class names (for default alert rule seeding)
SECURITY_CLASS_NAMES: list[str] = [c.name for c in COCO_CLASSES if c.security_relevant]


def class_name(index: int) -> str:
    """Return the class name for a YOLOX output class index, or 'unknown'."""
    return BY_INDEX.get(index, CocoClass(-1, "unknown", ClassGroup.EVERYDAY_OBJECTS)).name


def class_group(index: int) -> ClassGroup | None:
    """Return the semantic group for a class index."""
    cls = BY_INDEX.get(index)
    return cls.group if cls else None


def group_summary() -> dict[str, list[str]]:
    """Return a dict of group_name → [class_name, ...] (useful for API docs)."""
    return {g.value: [c.name for c in classes] for g, classes in BY_GROUP.items()}
