"""Portable diagram archive service.

An exported archive is deliberately independent from ARIADNE's internal JSON
repository.  It contains only the active diagram snapshot and image files that
are referenced by shapes in that diagram.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from ..utils.image_handler import get_image_handler


class ProjectArchiveService:
    def __init__(self, exporter):
        self.exporter = exporter
        self.last_export_warnings: list[str] = []

    def export_zip(self, diagram, zip_path: str, product_id=None) -> bool:
        """Export *diagram* as ``diagram.json`` plus its available images.

        ``product_id`` is accepted for backwards compatibility, but is
        intentionally ignored: exporting must not read from or write to the
        application's internal repository.

        Missing referenced images are skipped and recorded in
        ``last_export_warnings``.  Real export errors are allowed to propagate
        so the controller can show the user the actual exception.
        """
        self.last_export_warnings = []

        target = Path(zip_path).expanduser()
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")
        target.parent.mkdir(parents=True, exist_ok=True)

        # Build the JSON only from the in-memory diagram.  No repository call.
        data = self.exporter.serialize_active_diagram(diagram)

        handler = get_image_handler()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "diagram.json",
                json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"),
            )

            seen: set[str] = set()
            for image_path in self._referenced_image_paths(diagram):
                full_path = Path(handler.get_full_path(image_path))
                if not full_path.is_file():
                    self.last_export_warnings.append(
                        f"Missing image skipped: {image_path}"
                    )
                    continue

                # Keep the path used by diagram.json so import can restore it.
                normalized = str(image_path).replace("\\", "/")
                if normalized.startswith("images/"):
                    relative = normalized[len("images/"):]
                else:
                    relative = full_path.name
                relative = relative.lstrip("/")
                arcname = f"images/{relative}"

                if arcname in seen:
                    continue
                zf.write(full_path, arcname)
                seen.add(arcname)

        return True

    @staticmethod
    def _referenced_image_paths(diagram):
        """Yield non-empty image references from active diagram shapes."""
        seen = set()
        for shape in diagram.shapes:
            image_path = ""
            properties = getattr(shape, "properties", None)
            if isinstance(properties, dict):
                image_path = properties.get("image_path", "") or ""
            if not image_path:
                image_path = getattr(shape, "image_path", "") or ""
            if image_path and image_path not in seen:
                seen.add(image_path)
                yield image_path

    def import_zip(self, zip_path: str):
        """Extract a portable archive, restore its images, and return a Diagram."""
        try:
            handler = get_image_handler()
            with tempfile.TemporaryDirectory(prefix="ariadne_import_") as temp:
                temp_dir = Path(temp)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    root = temp_dir.resolve()
                    for member in zf.infolist():
                        dest = (temp_dir / member.filename).resolve()
                        if dest != root and root not in dest.parents:
                            raise ValueError("Unsafe archive path")
                    zf.extractall(temp_dir)

                json_path = temp_dir / "diagram.json"
                if not json_path.exists():
                    return None

                images_dir = temp_dir / "images"
                if images_dir.exists():
                    for source in images_dir.rglob("*"):
                        if not source.is_file():
                            continue
                        rel = source.relative_to(images_dir)
                        dest = Path(handler.images_dir) / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)

                return self.exporter.import_diagram(
                    str(json_path), create_in_repository=False
                )
        except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
            return None
