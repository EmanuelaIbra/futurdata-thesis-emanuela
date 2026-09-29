import tkinter as tk

from .controllers import AppController
from .views import MainWindow


def main():
    root = tk.Tk()

    controller = AppController()
    main_window = MainWindow(root, controller)
    controller.set_view(main_window)

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')

    root.mainloop()


if __name__ == "__main__":
    main()
