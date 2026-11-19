"""Interactive polygon annotation tool for the UOB Innovation Hub facade audit.

The tool reads frames from an exported SfM run and stores conservative facade
regions in preview-image coordinates.  It is intentionally separate from the
reconstruction pipeline: annotations are evaluation data, not SfM inputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk


DEFAULT_IMAGE_IDS = (3, 4, 5, 23, 24, 25, 35, 36, 37)
DEFAULT_PREVIEW_SIZE = (360, 640)


def parse_image_ids(value: str) -> list[int]:
    ids = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not ids or len(ids) != len(set(ids)):
        raise argparse.ArgumentTypeError("image IDs must be a non-empty, unique comma-separated list")
    return ids


def initial_document(inputs: dict, image_ids: list[int], preview_size: tuple[int, int]) -> dict:
    frames = {int(frame["id"]): frame for frame in inputs["frames"]}
    missing = [image_id for image_id in image_ids if image_id not in frames]
    if missing:
        raise ValueError(f"image IDs are absent from the run: {missing}")
    return {
        "annotation": (
            "Conservative manually traced UOB Innovation Hub facade regions. "
            "Sky, road, vegetation, signs, lamp posts, vehicles and uncertain occlusions are excluded. "
            "These polygons are evaluation labels only and are not used by reconstruction."
        ),
        "video_sha256": inputs["sha256"],
        "region_label": "facade",
        "preview_size": list(preview_size),
        "required_active_views": 2,
        "erosion_preview_px": 2,
        "selected_image_ids": image_ids,
        "polygons_by_source_frame": {
            str(frames[image_id]["source_frame"]): [] for image_id in image_ids
        },
    }


def load_or_initialize(output: Path, inputs: dict, image_ids: list[int],
                       preview_size: tuple[int, int]) -> dict:
    if not output.exists():
        return initial_document(inputs, image_ids, preview_size)
    document = json.loads(output.read_text(encoding="utf-8"))
    if document.get("video_sha256") != inputs["sha256"]:
        raise ValueError("existing annotations belong to a different input video")
    if tuple(document.get("preview_size", ())) != preview_size:
        raise ValueError("existing annotation preview size does not match --preview-size")
    if document.get("selected_image_ids") != image_ids:
        raise ValueError("existing annotation image selection does not match --image-ids")
    document.setdefault("region_label", "facade")
    return document


def save_document(output: Path, document: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(output)


class FacadeAnnotator:
    def __init__(self, root: tk.Tk, run: Path, output: Path, document: dict, inputs: dict):
        self.root = root
        self.run = run
        self.output = output
        self.document = document
        self.preview_width, self.preview_height = document["preview_size"]
        frames_by_id = {int(frame["id"]): frame for frame in inputs["frames"]}
        self.frames = [frames_by_id[image_id] for image_id in document["selected_image_ids"]]
        self.index = 0
        self.current_polygon: list[list[int]] = []
        self.photo = None
        self.dirty = False

        root.title("UOB Innovation Hub facade annotation")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.quit)

        content = tk.Frame(root, padx=8, pady=8)
        content.pack()
        self.canvas = tk.Canvas(
            content, width=self.preview_width, height=self.preview_height,
            background="#202020", highlightthickness=1, highlightbackground="#555555"
        )
        self.canvas.grid(row=0, column=0, rowspan=20, sticky="n")
        self.canvas.bind("<Button-1>", self.add_vertex)
        self.canvas.bind("<Shift-Button-1>", self.delete_polygon_at)
        self.canvas.bind("<Button-3>", lambda _event: self.close_polygon())

        sidebar = tk.Frame(content, width=300, padx=14)
        sidebar.grid(row=0, column=1, sticky="n")
        sidebar.grid_propagate(False)

        tk.Label(sidebar, text="Hive 建筑立面标注", font=("Segoe UI", 15, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 8))
        instructions = (
            "左键：添加多边形顶点\n"
            "Shift + 左键：删除点击位置的多边形\n"
            "右键或 Enter：闭合当前多边形\n"
            "Backspace：撤销一个顶点\n"
            "Delete：删除本图最后一个多边形\n"
            "← / →：上一张 / 下一张\n"
            "Ctrl+S：保存\n\n"
            "只圈清晰可见的圆筒楼体立面；排除天空、道路、树木、路灯、标牌、车辆和遮挡。"
        )
        tk.Label(sidebar, text=instructions, justify="left", anchor="w", wraplength=280,
                 font=("Microsoft YaHei UI", 10)).pack(fill="x", pady=(0, 12))

        self.status = tk.Label(sidebar, justify="left", anchor="w", wraplength=280,
                               font=("Consolas", 10))
        self.status.pack(fill="x", pady=(0, 12))

        for label, command in (
            ("闭合多边形 (Enter)", self.close_polygon),
            ("撤销顶点 (Backspace)", self.undo_vertex),
            ("删除本图最后一个多边形 (Delete)", self.delete_polygon),
            ("上一张 (←)", self.previous_frame),
            ("下一张 (→)", self.next_frame),
            ("保存 (Ctrl+S)", self.save),
            ("保存并退出", self.save_and_quit),
        ):
            tk.Button(sidebar, text=label, command=command, width=30, pady=5).pack(pady=2)

        root.bind("<Return>", lambda _event: self.close_polygon())
        root.bind("<BackSpace>", lambda _event: self.undo_vertex())
        root.bind("<Delete>", lambda _event: self.delete_polygon())
        root.bind("<Left>", lambda _event: self.previous_frame())
        root.bind("<Right>", lambda _event: self.next_frame())
        root.bind("<Control-s>", lambda _event: self.save())
        root.bind("<Control-S>", lambda _event: self.save())
        self.render()

    @property
    def frame(self) -> dict:
        return self.frames[self.index]

    @property
    def source_key(self) -> str:
        return str(self.frame["source_frame"])

    @property
    def polygons(self) -> list[list[list[int]]]:
        return self.document["polygons_by_source_frame"][self.source_key]

    def render(self) -> None:
        source = Image.open(self.run / self.frame["file"]).convert("RGB")
        source = source.resize((self.preview_width, self.preview_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(source)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for polygon in self.polygons:
            flat = [coordinate for point in polygon for coordinate in point]
            self.canvas.create_polygon(
                flat, outline="#35e394", fill="#35e394", stipple="gray25", width=2
            )
        if self.current_polygon:
            flat = [coordinate for point in self.current_polygon for coordinate in point]
            if len(self.current_polygon) > 1:
                self.canvas.create_line(*flat, fill="#ffe45c", width=3)
            for x, y in self.current_polygon:
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                                        fill="#ffe45c", outline="#202020")
        completed = sum(bool(polygons) for polygons in
                        self.document["polygons_by_source_frame"].values())
        self.status.configure(text=(
            f"图片 {self.index + 1}/{len(self.frames)}\n"
            f"工作图 ID: {self.frame['id']:03d}\n"
            f"视频源帧: {self.frame['source_frame']:04d}\n"
            f"本图多边形: {len(self.polygons)}\n"
            f"已标注图片: {completed}/{len(self.frames)}\n"
            f"状态: {'未保存' if self.dirty else '已保存'}"
        ))

    def add_vertex(self, event: tk.Event) -> None:
        self.current_polygon.append([int(event.x), int(event.y)])
        self.dirty = True
        self.render()

    @staticmethod
    def point_in_polygon(x: int, y: int, polygon: list[list[int]]) -> bool:
        inside = False
        previous_x, previous_y = polygon[-1]
        for current_x, current_y in polygon:
            crosses = (current_y > y) != (previous_y > y)
            if crosses:
                boundary_x = ((previous_x - current_x) * (y - current_y)
                              / (previous_y - current_y) + current_x)
                if x < boundary_x:
                    inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    def delete_polygon_at(self, event: tk.Event) -> str:
        if self.current_polygon:
            messagebox.showwarning("先结束当前多边形", "请先按 Enter 闭合或按 Delete 取消当前多边形。")
            return "break"
        for index in range(len(self.polygons) - 1, -1, -1):
            if not self.point_in_polygon(event.x, event.y, self.polygons[index]):
                continue
            if messagebox.askyesno("删除多边形", "删除点击位置的绿色多边形吗？"):
                self.polygons.pop(index)
                self.dirty = True
                self.render()
            return "break"
        messagebox.showinfo("没有多边形", "点击位置不在任何已完成的绿色多边形内。")
        return "break"

    def close_polygon(self) -> bool:
        if not self.current_polygon:
            return True
        if len(self.current_polygon) < 3:
            messagebox.showwarning("顶点不足", "一个多边形至少需要三个顶点。")
            return False
        self.polygons.append(self.current_polygon)
        self.current_polygon = []
        self.dirty = True
        self.render()
        return True

    def undo_vertex(self) -> None:
        if self.current_polygon:
            self.current_polygon.pop()
            self.dirty = True
            self.render()

    def delete_polygon(self) -> None:
        if self.current_polygon:
            self.current_polygon = []
        elif self.polygons:
            self.polygons.pop()
        else:
            return
        self.dirty = True
        self.render()

    def change_frame(self, step: int) -> None:
        if not self.close_polygon():
            return
        self.index = max(0, min(len(self.frames) - 1, self.index + step))
        self.render()

    def previous_frame(self) -> None:
        self.change_frame(-1)

    def next_frame(self) -> None:
        self.change_frame(1)

    def save(self) -> None:
        if not self.close_polygon():
            return
        save_document(self.output, self.document)
        self.dirty = False
        self.render()

    def save_and_quit(self) -> None:
        if not self.close_polygon():
            return
        self.save()
        self.root.destroy()

    def quit(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel("保存标注", "退出前保存当前标注吗？")
            if answer is None:
                return
            if answer:
                self.save()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path,
                        default=Path("report_reference/results/hive/the_hive_test2"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/evaluation/hive_facade_regions.json"))
    parser.add_argument("--image-ids", type=parse_image_ids,
                        default=list(DEFAULT_IMAGE_IDS),
                        help="comma-separated exported image IDs")
    parser.add_argument("--preview-size", default="360,640",
                        help="annotation canvas width,height")
    parser.add_argument("--initialize-only", action="store_true",
                        help="create or validate the JSON template without opening the GUI")
    args = parser.parse_args()

    preview_size = tuple(int(value) for value in args.preview_size.split(","))
    if len(preview_size) != 2 or min(preview_size) <= 0:
        parser.error("--preview-size must be positive width,height")
    run = args.run.resolve()
    output = args.output.resolve()
    inputs = json.loads((run / "inputs.json").read_text(encoding="utf-8"))
    document = load_or_initialize(output, inputs, args.image_ids, preview_size)
    if args.initialize_only:
        save_document(output, document)
        print(f"Annotation template ready: {output}")
        return

    root = tk.Tk()
    FacadeAnnotator(root, run, output, document, inputs)
    root.mainloop()


if __name__ == "__main__":
    main()
