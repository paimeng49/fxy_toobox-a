import customtkinter as ctk
import webbrowser
from config import settings

class SitesPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.title = ctk.CTkLabel(self, text="实用网站", font=("Arial", 20, "bold"))
        self.title.pack(pady=10)
        
        # 创建可滚动区域
        self.scroll_frame = ctk.CTkScrollableFrame(self, width=600, height=400)
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 生成网格卡片
        for i, (name, url) in enumerate(settings.USEFUL_SITES):
            # 每行2个
            row = i // 2
            col = i % 2
            card = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            self.scroll_frame.grid_columnconfigure(0, weight=1)
            self.scroll_frame.grid_columnconfigure(1, weight=1)
            
            site_name = ctk.CTkLabel(card, text=name, font=("Arial", 14, "bold"))
            site_name.pack(pady=10)
            
            site_url = ctk.CTkLabel(card, text=url, font=("Arial", 10), fg_color="gray")
            site_url.pack(pady=5, padx=10, fill="x")
            
            open_btn = ctk.CTkButton(card, text="打开", command=lambda u=url: webbrowser.open(u))
            open_btn.pack(pady=10)