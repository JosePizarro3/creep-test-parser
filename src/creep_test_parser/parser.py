from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from bam_masterdata.metadata.definitions import DataType
from bam_masterdata.metadata.entities import CollectionType, ObjectType
from bam_masterdata.parsing import AbstractParser

from creep_test_parser.annotations import ANNOTATIONS, FieldMapping

CATEGORY_COLUMNS = (
    "category_i",
    "category_ii",
    "category_iii",
    "category_iv",
)
ENTRY_COLUMN = "entry"
VALUE_COLUMN = "answer_options"


class BaseFileParser(ABC):
    @abstractmethod
    def custom_parser(self) -> dict[str, pd.DataFrame]:
        """Return normalized dataframes keyed by sheet name."""
        raise NotImplementedError


class ExcelParser(BaseFileParser):
    """Read creep-test Excel files and normalize their schema rows.

    The template header is not assumed to be on a fixed row. Instead, the first
    rows of every sheet are searched for a row containing at least ``ENTRY`` and
    an answer/value column. Sheets that do not look like schema sheets are
    ignored.
    """

    HEADER_SCAN_ROWS = 30

    # After normalization, all of these become candidates for the canonical
    # column name on the right.
    COLUMN_ALIASES = {
        "category_i": "category_i",
        "category_1": "category_i",
        "category_ii": "category_ii",
        "category_2": "category_ii",
        "category_iii": "category_iii",
        "category_3": "category_iii",
        "category_iv": "category_iv",
        "category_4": "category_iv",
        "entry": ENTRY_COLUMN,
        "answer_options": VALUE_COLUMN,
        "answer_option": VALUE_COLUMN,
        "answer": VALUE_COLUMN,
        "value": VALUE_COLUMN,
    }

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)

    @staticmethod
    def _normalize_column_name(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        text = str(value).strip().casefold()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return text.strip("_")

    @classmethod
    def _canonical_column_name(cls, value: Any) -> str:
        normalized = cls._normalize_column_name(value)
        return cls.COLUMN_ALIASES.get(normalized, normalized)

    @classmethod
    def _find_header_row(cls, df: pd.DataFrame) -> int | None:
        max_rows = min(len(df), cls.HEADER_SCAN_ROWS)
        for row_index in range(max_rows):
            columns = {
                cls._canonical_column_name(value)
                for value in df.iloc[row_index].tolist()
            }
            if ENTRY_COLUMN in columns and VALUE_COLUMN in columns:
                return row_index
        return None

    @staticmethod
    def _deduplicate_columns(columns: list[str]) -> list[str]:
        """Make duplicate normalized headers deterministic for pandas indexing."""
        counts: Counter[str] = Counter()
        result: list[str] = []
        for column in columns:
            if not column:
                column = "unnamed"
            counts[column] += 1
            if counts[column] == 1:
                result.append(column)
            else:
                result.append(f"{column}_{counts[column]}")
        return result

    def custom_parser(self) -> dict[str, pd.DataFrame]:
        try:
            source = pd.read_excel(
                self.filepath,
                sheet_name=None,
                header=None,
                engine="openpyxl",
                dtype=object,
            )
        except (OSError, ValueError, ImportError) as exc:
            raise ValueError(
                f"Could not read Excel file '{self.filepath}': {exc}"
            ) from exc

        parsed: dict[str, pd.DataFrame] = {}

        for sheet_name, raw_df in source.items():
            if raw_df.empty:
                continue

            header_row = self._find_header_row(raw_df)
            if header_row is None:
                continue

            headers = [
                self._canonical_column_name(value)
                for value in raw_df.iloc[header_row].tolist()
            ]
            headers = self._deduplicate_columns(headers)

            df = raw_df.iloc[header_row + 1 :].copy()
            df.columns = headers
            # Excel row numbers are 1-based. Preserve them for diagnostics before
            # resetting the dataframe index.
            df["_excel_row"] = df.index + 1
            df = df.reset_index(drop=True)

            # Keep only rows that actually describe a schema entry.
            if ENTRY_COLUMN not in df.columns or VALUE_COLUMN not in df.columns:
                continue

            df = df[df[ENTRY_COLUMN].notna()].copy()
            if df.empty:
                continue

            parsed[sheet_name] = df

        return parsed


class CreepTestParser(AbstractParser):
    """Map creep-test Excel template content into bam-masterdata objects."""

    def __init__(self) -> None:
        self.annotation_index = self._build_annotation_index(ANNOTATIONS)

    # ------------------------------------------------------------------
    # Annotation lookup
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_label(value: Any) -> str | None:
        """Normalize labels while preserving their semantic wording.

        This intentionally collapses whitespace/newlines and ignores case so
        minor template formatting changes do not break annotation lookup.
        """
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        text = str(value).replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text.casefold() or None

    @classmethod
    def _build_annotation_index(
        cls, annotations: dict[str, Any]
    ) -> dict[tuple[str | None, ...], FieldMapping | None]:
        """Flatten nested ANNOTATIONS into normalized hierarchy tuples.

        Expected paths are CATEGORY I -> CATEGORY II -> CATEGORY III ->
        optional CATEGORY IV -> ENTRY.
        """
        index: dict[tuple[str | None, ...], FieldMapping | None] = {}

        def walk(node: Any, path: list[str]) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, [*path, key])
                return

            if len(path) not in (4, 5):
                raise ValueError(
                    "Invalid ANNOTATIONS leaf path. Expected 4 levels "
                    "(CATEGORY I-III + ENTRY) or 5 levels "
                    "(CATEGORY I-IV + ENTRY), got: " + " > ".join(path)
                )

            if len(path) == 4:
                cat_i, cat_ii, cat_iii, entry = path
                cat_iv = None
            else:
                cat_i, cat_ii, cat_iii, cat_iv, entry = path

            normalized_key = tuple(
                cls._normalize_label(value)
                for value in (cat_i, cat_ii, cat_iii, cat_iv, entry)
            )
            if normalized_key in index:
                raise ValueError(
                    f"Duplicate normalized ANNOTATIONS path detected: {normalized_key}"
                )
            index[normalized_key] = node

        walk(annotations, [])
        return index

    def _lookup_mapping(self, row: pd.Series) -> FieldMapping | None | object:
        key = tuple(
            self._normalize_label(row.get(column))
            for column in (*CATEGORY_COLUMNS, ENTRY_COLUMN)
        )
        return self.annotation_index.get(key, _MISSING)

    # ------------------------------------------------------------------
    # Value handling
    # ------------------------------------------------------------------
    @staticmethod
    def _is_blank(value: Any) -> bool:
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass
        if isinstance(value, str):
            return value.strip().casefold() in {"", "nan", "n/a", "not applicable"}
        return False

    @staticmethod
    def _display_path(row: pd.Series) -> str:
        parts = []
        for column in (*CATEGORY_COLUMNS, ENTRY_COLUMN):
            value = row.get(column)
            if CreepTestParser._is_blank(value):
                continue
            parts.append(str(value).strip())
        return " > ".join(parts)

    @staticmethod
    def _get_or_create_object(
        object_type: type[ObjectType],
        objects: dict[type[ObjectType], ObjectType],
    ) -> ObjectType:
        obj = objects.get(object_type)
        if obj is None:
            obj = object_type()
            objects[object_type] = obj
        return obj

    def _apply_mapping(
        self,
        *,
        mapping: FieldMapping,
        raw_value: Any,
        objects: dict[type[ObjectType], ObjectType],
        touched_fields: dict[type[ObjectType], set[str]],
        logger,
        source: str,
    ) -> bool:
        """Apply one mapped value. Returns True when a property was assigned."""
        if self._is_blank(raw_value):
            return False

        obj = self._get_or_create_object(mapping.object_type, objects)

        try:
            value = mapping.convert(raw_value)
        except (TypeError, ValueError, AttributeError) as exc:
            logger.error(f"CreepTestParser: conversion failed for {source}: {exc}")
            return False

        if value is None:
            return False

        try:
            if mapping.merger is not None:
                current = getattr(obj, mapping.property_map, None)
                # Unset model properties are class-level PropertyTypeAssignment
                # descriptors. They are not real existing values to merge.
                if mapping.property_map in getattr(obj, "_property_metadata", {}):
                    prop_def = obj._property_metadata[mapping.property_map]
                    if current is prop_def:
                        current = None
                value = mapping.merger(current, value)

            setattr(obj, mapping.property_map, value)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            logger.error(
                f"CreepTestParser: assignment failed for {source} -> "
                f"{mapping.object_type.__name__}.{mapping.property_map}: {exc}"
            )
            return False

        touched_fields[mapping.object_type].add(mapping.property_map)
        return True

    # ------------------------------------------------------------------
    # Collection / relationship handling
    # ------------------------------------------------------------------
    @staticmethod
    def _object_code(object_type: type[ObjectType]) -> str | None:
        defs = getattr(object_type, "defs", None)
        return getattr(defs, "code", None)

    @classmethod
    def _find_link_property(
        cls,
        parent: ObjectType,
        child: ObjectType,
    ) -> str | None:
        """Return the parent's link_ property that points to the child type."""
        child_code = cls._object_code(type(child))
        if not child_code:
            return None

        for property_name, property_def in parent._property_metadata.items():
            if not property_name.startswith("link_"):
                continue
            if property_def.data_type != DataType.OBJECT:
                continue
            if property_def.object_code == child_code:
                return property_name
        return None

    @classmethod
    def _relationship_edges(
        cls,
        objects: dict[type[ObjectType], ObjectType],
    ) -> list[tuple[type[ObjectType], type[ObjectType], str]]:
        """Derive parent-child edges from link_ OBJECT properties in the model."""
        edges: list[tuple[type[ObjectType], type[ObjectType], str]] = []
        values = list(objects.values())

        for parent in values:
            for child in values:
                if parent is child:
                    continue
                link_property = cls._find_link_property(parent, child)
                if link_property is not None:
                    edges.append((type(parent), type(child), link_property))

        return edges

    @staticmethod
    def _add_objects(
        *,
        collection: CollectionType,
        objects: dict[type[ObjectType], ObjectType],
        touched_fields: dict[type[ObjectType], set[str]],
        logger,
        filepath: Path,
    ) -> dict[type[ObjectType], str]:
        object_ids: dict[type[ObjectType], str] = {}

        # Only add objects that received at least one actual value.
        for object_type, obj in objects.items():
            if not touched_fields.get(object_type):
                continue

            try:
                object_id = collection.add(obj)
            except (TypeError, ValueError, KeyError, AttributeError) as exc:
                logger.error(
                    f"CreepTestParser: could not add {object_type.__name__} "
                    f"from '{filepath}': {exc}"
                )
                continue

            object_ids[object_type] = object_id

        return object_ids

    @staticmethod
    def _add_relationships(
        *,
        collection: CollectionType,
        object_ids: dict[type[ObjectType], str],
        edges: list[tuple[type[ObjectType], type[ObjectType], str]],
        logger,
        filepath: Path,
    ) -> int:
        added = 0

        for parent_type, child_type, link_property in edges:
            parent_id = object_ids.get(parent_type)
            child_id = object_ids.get(child_type)
            if parent_id is None or child_id is None:
                continue

            try:
                collection.add_relationship(parent=parent_id, child=child_id)
            except (TypeError, ValueError, KeyError) as exc:
                logger.error(
                    f"CreepTestParser: could not add relationship "
                    f"{parent_type.__name__}.{link_property} -> "
                    f"{child_type.__name__} for '{filepath}': {exc}"
                )
                continue

            added += 1

        return added

    # ------------------------------------------------------------------
    # Public parser API
    # ------------------------------------------------------------------
    def parse(self, files: list[str], collection: CollectionType, logger) -> None:
        for filename in files:
            filepath = Path(filename)

            if filepath.suffix.casefold() != ".xlsx":
                logger.error(
                    f"CreepTestParser: unsupported file type '{filepath.suffix}' "
                    f"for '{filepath}'"
                )
                continue

            if not filepath.is_file():
                logger.error(f"CreepTestParser: file does not exist: '{filepath}'")
                continue

            try:
                sheets = ExcelParser(filepath).custom_parser()
            except Exception as exc:
                # File-level failure: continue with the next workbook. This is
                # deliberately broad because corrupt/odd Excel files can raise
                # several library-specific exception types.
                logger.exception(f"CreepTestParser: failed to read '{filepath}': {exc}")
                continue

            if not sheets:
                logger.error(
                    f"CreepTestParser: no recognizable creep-test schema sheets "
                    f"found in '{filepath}'"
                )
                continue

            objects: dict[type[ObjectType], ObjectType] = {}
            touched_fields: dict[type[ObjectType], set[str]] = defaultdict(set)

            stats = Counter()

            for sheet_name, df in sheets.items():
                logger.info(
                    f"CreepTestParser: processing '{filepath.name}' / sheet '{sheet_name}'"
                )

                # CATEGORY IV is optional and some template versions may not
                # contain the column at all.
                for column in CATEGORY_COLUMNS:
                    if column not in df.columns:
                        df[column] = None

                for row_index, row in df.iterrows():
                    stats["rows"] += 1
                    source = (
                        f"'{filepath.name}', sheet '{sheet_name}', "
                        f"row {row.get('_excel_row', row_index + 1)}: "
                        f"{self._display_path(row)}"
                    )

                    mapping = self._lookup_mapping(row)

                    if mapping is _MISSING:
                        stats["unmapped"] += 1
                        logger.warning(
                            f"CreepTestParser: no annotation mapping for {source}"
                        )
                        continue

                    if mapping is None:
                        stats["ignored"] += 1
                        continue

                    raw_value = row.get(VALUE_COLUMN)
                    if self._is_blank(raw_value):
                        stats["blank"] += 1
                        continue

                    if self._apply_mapping(
                        mapping=mapping,
                        raw_value=raw_value,
                        objects=objects,
                        touched_fields=touched_fields,
                        logger=logger,
                        source=source,
                    ):
                        stats["mapped"] += 1
                    else:
                        stats["failed"] += 1

            edges = self._relationship_edges(objects)
            object_ids = self._add_objects(
                collection=collection,
                objects=objects,
                touched_fields=touched_fields,
                logger=logger,
                filepath=filepath,
            )
            relationship_count = self._add_relationships(
                collection=collection,
                object_ids=object_ids,
                edges=edges,
                logger=logger,
                filepath=filepath,
            )

            logger.info(
                "CreepTestParser: completed "
                f"'{filepath.name}': rows={stats['rows']}, "
                f"mapped={stats['mapped']}, blank={stats['blank']}, "
                f"ignored={stats['ignored']}, unmapped={stats['unmapped']}, "
                f"failed={stats['failed']}, objects={len(object_ids)}, "
                f"relationships={relationship_count}"
            )


_MISSING = object()
