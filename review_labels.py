import os
import sys
import csv
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import cv2

# --- CONFIGURATION ---
IMAGE_DIR = "ball_dataset_v2/images"
LABEL_DIR = "ball_dataset_v2/labels"
OUTPUT_CSV = "review_results.csv"

class LabelReviewerApp:
    def __init__(self, root, image_dir, label_dir, output_csv):
        self.root = root
        self.image_dir = image_dir
        self.label_dir = label_dir
        self.output_csv = output_csv
        
        self.root.title("YOLO Dataset Label Review Utility")
        self.root.geometry("1000x800")
        
        # Load state
        self.image_files = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
        self.current_index = 0
        self.review_data = {}
        
        if not self.image_files:
            messagebox.showerror("Error", f"No images found in {image_dir}")
            sys.exit(1)
            
        self.load_existing_results()
        self.setup_ui()
        
        self.root.bind("a", lambda event: self.record_status("accepted"))
        self.root.bind("r", lambda event: self.record_status("rejected"))
        self.root.bind("s", lambda event: self.record_status("uncertain"))
        self.root.bind("<Left>", lambda event: self.navigate(-1))
        self.root.bind("<Right>", lambda event: self.navigate(1))
        
        self.display_current_image()

    def setup_ui(self):
        self.meta_frame = tk.Frame(self.root, bg="#f0f0f0", pady=10, padx=10)
        self.meta_frame.pack(fill=tk.X)
        
        self.file_label = tk.Label(self.meta_frame, text="", font=("Arial", 12, "bold"), bg="#f0f0f0")
        self.file_label.pack(anchor=tk.W)
        
        self.coord_label = tk.Label(self.meta_frame, text="", font=("Courier", 10), bg="#f0f0f0", justify=tk.LEFT)
        self.coord_label.pack(anchor=tk.W)
        
        self.progress_label = tk.Label(self.meta_frame, text="", font=("Arial", 10), bg="#f0f0f0")
        self.progress_label.pack(anchor=tk.E)

        self.canvas_frame = tk.Frame(self.root, bg="#222222")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.image_label = tk.Label(self.canvas_frame, bg="#222222")
        self.image_label.pack(fill=tk.BOTH, expand=True)

        self.control_frame = tk.Frame(self.root, pady=15)
        self.control_frame.pack(fill=tk.X)
        
        btn_opts = {"font": ("Arial", 11, "bold"), "width": 15, "pady": 5}
        
        tk.Button(self.control_frame, text="Accept (A)", bg="#d4edda", fg="#155724", command=lambda: self.record_status("accepted"), **btn_opts).pack(side=tk.LEFT, padx=10, expand=True)
        tk.Button(self.control_frame, text="Reject (R)", bg="#f8d7da", fg="#721c24", command=lambda: self.record_status("rejected"), **btn_opts).pack(side=tk.LEFT, padx=10, expand=True)
        tk.Button(self.control_frame, text="Uncertain (S)", bg="#fff3cd", fg="#856404", command=lambda: self.record_status("uncertain"), **btn_opts).pack(side=tk.LEFT, padx=10, expand=True)
        
        tk.Button(self.control_frame, text="◀ Back", command=lambda: self.navigate(-1)).pack(side=tk.LEFT, padx=5)
        tk.Button(self.control_frame, text="Next ▶", command=lambda: self.navigate(1)).pack(side=tk.LEFT, padx=5)

    def load_existing_results(self):
        if os.path.exists(self.output_csv):
            with open(self.output_csv, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) == 2:
                        self.review_data[row[0]] = row[1]
            
            for idx, img_name in enumerate(self.image_files):
                if img_name not in self.review_data:
                    self.current_index = idx
                    break
            else:
                self.current_index = len(self.image_files) - 1

    def save_results(self):
        with open(self.output_csv, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["image_file", "status"])
            for img_name in self.image_files:
                status = self.review_data.get(img_name, "")
                writer.writerow([img_name, status])

    def get_yolo_labels(self, img_name):
        base_name = os.path.splitext(img_name)[0]
        label_file = os.path.join(self.label_dir, f"{base_name}.txt")
        boxes = []
        if os.path.exists(label_file):
            with open(label_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        boxes.append([float(x) for x in parts[:5]])
        return boxes

    def display_current_image(self):
        if 0 <= self.current_index < len(self.image_files):
            img_name = self.image_files[self.current_index]
            img_path = os.path.join(self.image_dir, img_name)
            
            status_text = self.review_data.get(img_name, "UNREVIEWED").upper()
            self.file_label.config(text=f"File: {img_name}   [{status_text}]", fg="#111" if status_text == "UNREVIEWED" else "#007bff")
            self.progress_label.config(text=f"Image {self.current_index + 1} of {len(self.image_files)}")
            
            cv_img = cv2.imread(img_path)
            if cv_img is None:
                self.coord_label.config(text="Error loading image file.")
                return
                
            h, w, _ = cv_img.shape
            boxes = self.get_yolo_labels(img_name)
            
            coord_str_list = []
            for box in boxes:
                cls, xc, yc, bw, bh = box
                coord_str_list.append(f"Class: {int(cls)} | Center: ({xc:.4f}, {yc:.4f}) | Size: {bw:.4f}x{bh:.4f}")
                
                x1 = int((xc - bw / 2) * w)
                y1 = int((yc - bh / 2) * h)
                x2 = int((xc + bw / 2) * w)
                y2 = int((yc + bh / 2) * h)
                
                cv2.rectangle(cv_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.circle(cv_img, (int(xc * w), int(yc * h)), 2, (0, 0, 255), -1)

            self.coord_label.config(text="\n".join(coord_str_list) if coord_str_list else "No boxes present in label file.")
            
            canvas_w = self.canvas_frame.winfo_width()
            canvas_h = self.canvas_frame.winfo_height()
            if canvas_w < 10: canvas_w = 800
            if canvas_h < 10: canvas_h = 600
            
            cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(cv_img)
            pil_img.thumbnail((canvas_w, canvas_h), Image.Resampling.LANCZOS)
            
            tk_img = ImageTk.PhotoImage(image=pil_img)
            self.image_label.configure(image=tk_img)
            self.image_label.image = tk_img
        else:
            self.file_label.config(text="Review complete!")
            self.coord_label.config(text="")
            self.image_label.configure(image="")

    def record_status(self, status):
        if self.current_index < len(self.image_files):
            img_name = self.image_files[self.current_index]
            self.review_data[img_name] = status
            self.save_results()
            self.navigate(1)

    def navigate(self, direction):
        new_index = self.current_index + direction
        if 0 <= new_index < len(self.image_files):
            self.current_index = new_index
            self.display_current_image()
        elif new_index >= len(self.image_files):
            messagebox.showinfo("End", "You have reached the end of the dataset files.")

if __name__ == "__main__":
    if not os.path.exists(IMAGE_DIR) or not os.path.exists(LABEL_DIR):
        print(f"Error: Target paths missing.\nImage Dir: {IMAGE_DIR}\nLabel Dir: {LABEL_DIR}")
        sys.exit(1)
        
    root = tk.Tk()
    app = LabelReviewerApp(root, IMAGE_DIR, LABEL_DIR, OUTPUT_CSV)
    root.update()
    app.display_current_image()
    root.mainloop()
