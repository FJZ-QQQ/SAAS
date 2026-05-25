"""
光宸智能客服 - 数据库管理工具
双击打开即可查看和管理数据库
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import psycopg2
import sys
import os
import hashlib
import secrets

# ========== 数据库配置 ==========
DB_URL = "postgresql://guangchen:gc2026@124.223.99.238:5432/guangchen_db"

def hash_password(password: str) -> str:
    salt = secrets.token_hex(12)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"

class DatabaseManager:
    def __init__(self, root):
        self.root = root
        self.root.title("光宸智能客服 - 数据库管理工具")
        self.set_window_icon()
        self.root.geometry("1000x650")
        self.root.configure(bg="#1e1e2e")
        
        self.conn = None
        self.current_table = None
        self.columns = []
        
        self.setup_styles()
        self.create_ui()
        self.connect_db()

    def set_window_icon(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.abspath(os.path.join(base_dir, "..", "douyin-rpa-desktop", "build", "icon.png"))
        if not os.path.exists(icon_path):
            return
        try:
            self._icon_image = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self._icon_image)
        except Exception:
            pass
        
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Microsoft YaHei", 16, "bold"), background="#1e1e2e", foreground="#cdd6f4")
        style.configure("Info.TLabel", font=("Microsoft YaHei", 10), background="#1e1e2e", foreground="#a6adc8")
        style.configure("TButton", font=("Microsoft YaHei", 10), padding=6)
        style.configure("Table.TButton", font=("Microsoft YaHei", 10, "bold"), padding=8)
        style.configure("Treeview", font=("Consolas", 10), rowheight=28, background="#313244", foreground="#cdd6f4", fieldbackground="#313244")
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"), background="#45475a", foreground="#cdd6f4")
        style.map("Treeview", background=[("selected", "#585b70")])
        
    def create_ui(self):
        # 顶部标题
        top = tk.Frame(self.root, bg="#1e1e2e")
        top.pack(fill="x", padx=15, pady=(15, 5))
        ttk.Label(top, text="📊 光宸数据库管理", style="Title.TLabel").pack(side="left")
        self.status_label = ttk.Label(top, text="未连接", style="Info.TLabel")
        self.status_label.pack(side="right")
        
        # 表按钮区
        self.table_frame = tk.Frame(self.root, bg="#1e1e2e")
        self.table_frame.pack(fill="x", padx=15, pady=5)
        
        # 操作按钮区
        action_frame = tk.Frame(self.root, bg="#1e1e2e")
        action_frame.pack(fill="x", padx=15, pady=5)
        
        btn_style = {"font": ("Microsoft YaHei", 10), "bg": "#45475a", "fg": "#cdd6f4", "relief": "flat", "padx": 12, "pady": 4, "cursor": "hand2"}
        
        tk.Button(action_frame, text="🔄 刷新", command=self.refresh_data, **btn_style).pack(side="left", padx=3)
        tk.Button(action_frame, text="➕ 新增商户", command=self.add_merchant, bg="#a6e3a1", fg="#1e1e2e", font=("Microsoft YaHei", 10, "bold"), relief="flat", padx=12, pady=4, cursor="hand2").pack(side="left", padx=3)
        tk.Button(action_frame, text="👑 新增管理员", command=self.add_admin, bg="#89b4fa", fg="#1e1e2e", font=("Microsoft YaHei", 10, "bold"), relief="flat", padx=12, pady=4, cursor="hand2").pack(side="left", padx=3)
        tk.Button(action_frame, text="💰 修改余额", command=self.edit_balance, bg="#f9e2af", fg="#1e1e2e", font=("Microsoft YaHei", 10, "bold"), relief="flat", padx=12, pady=4, cursor="hand2").pack(side="left", padx=3)
        tk.Button(action_frame, text="🔑 重置密码", command=self.reset_password, bg="#cba6f7", fg="#1e1e2e", font=("Microsoft YaHei", 10, "bold"), relief="flat", padx=12, pady=4, cursor="hand2").pack(side="left", padx=3)
        tk.Button(action_frame, text="🗑️ 删除选中", command=self.delete_row, bg="#f38ba8", fg="#1e1e2e", font=("Microsoft YaHei", 10), relief="flat", padx=12, pady=4, cursor="hand2").pack(side="left", padx=3)
        
        # 数据表格
        table_container = tk.Frame(self.root, bg="#313244")
        table_container.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        
        self.tree = ttk.Treeview(table_container, show="headings", selectmode="browse")
        
        vsb = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)
        
        # 底部统计
        self.bottom_label = ttk.Label(self.root, text="", style="Info.TLabel")
        self.bottom_label.pack(padx=15, pady=(0, 10))
        
    def connect_db(self):
        try:
            self.conn = psycopg2.connect(DB_URL, connect_timeout=5)
            self.conn.autocommit = True
            self.ensure_schema()
            self.status_label.config(text="✅ 已连接 124.223.99.238")
            self.load_tables()
        except Exception as e:
            self.status_label.config(text="❌ 连接失败")
            messagebox.showerror("连接失败", f"无法连接数据库：\n{e}")

    def ensure_schema(self):
        try:
            cur = self.conn.cursor()
            cur.execute("ALTER TABLE merchant ALTER COLUMN password_hash TYPE TEXT")
            cur.execute("ALTER TABLE admin_user ALTER COLUMN password TYPE TEXT")
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ai_agent' AND column_name = 'slot_id'
                LIMIT 1
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE ai_agent ADD COLUMN IF NOT EXISTS slot_id INTEGER")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_agent_merchant_slot ON ai_agent(merchant_id, slot_id)")
            cur.close()
        except Exception:
            # 当前线上账号没有改表权限；密码哈希已控制在 varchar(100) 内，可正常写入。
            pass
            
    def load_tables(self):
        # 清除旧按钮
        for w in self.table_frame.winfo_children():
            w.destroy()
            
        ttk.Label(self.table_frame, text="选择表：", style="Info.TLabel").pack(side="left", padx=(0, 5))
        
        cur = self.conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = [r[0] for r in cur.fetchall()]
        
        table_names = {
            "admin_user": "👑 管理员",
            "merchant": "👤 商户",
            "ai_agent": "🤖 AI配置",
            "customer_lead": "📋 客资",
            "rpa_slot": "🔧 RPA状态",
            "chat_session": "💬 会话",
            "chat_message": "📝 消息",
        }
        
        for t in tables:
            label = table_names.get(t, t)
            btn = tk.Button(
                self.table_frame, text=label,
                font=("Microsoft YaHei", 10, "bold"),
                bg="#89b4fa" if t == self.current_table else "#45475a",
                fg="#1e1e2e" if t == self.current_table else "#cdd6f4",
                relief="flat", padx=15, pady=4, cursor="hand2",
                command=lambda name=t: self.show_table(name)
            )
            btn.pack(side="left", padx=3)
            
        # 默认显示商户表
        if not self.current_table and tables:
            self.show_table("merchant" if "merchant" in tables else tables[0])
            
    def show_table(self, table_name):
        self.current_table = table_name
        self.load_tables()  # 刷新按钮高亮
        self.refresh_data()
        
    def refresh_data(self):
        if not self.current_table:
            return
            
        try:
            cur = self.conn.cursor()
            
            # 获取列信息
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{self.current_table}' ORDER BY ordinal_position")
            self.columns = [r[0] for r in cur.fetchall()]
            
            # 配置表头
            self.tree["columns"] = self.columns
            for col in self.columns:
                self.tree.heading(col, text=col)
                width = 150 if col in ("persona", "knowledge_base", "content", "needs") else 100
                self.tree.column(col, width=width, minwidth=60)
                
            # 清除旧数据
            for item in self.tree.get_children():
                self.tree.delete(item)
                
            # 获取数据
            cur.execute(f"SELECT * FROM {self.current_table} ORDER BY id DESC LIMIT 500")
            rows = cur.fetchall()
            
            for row in rows:
                display = []
                for val in row:
                    s = str(val) if val is not None else ""
                    if len(s) > 80:
                        s = s[:80] + "..."
                    display.append(s)
                self.tree.insert("", "end", values=display)
                
            self.bottom_label.config(text=f"表 {self.current_table} | 共 {len(rows)} 条记录")
            
        except Exception as e:
            messagebox.showerror("查询错误", str(e))
            
    def add_merchant(self):
        """新增商户"""
        win = tk.Toplevel(self.root)
        win.title("新增商户")
        win.geometry("350x280")
        win.configure(bg="#1e1e2e")
        win.grab_set()
        
        fields = {}
        labels = [("手机号", "phone"), ("密码", "password"), ("初始余额", "balance")]
        
        for i, (label, key) in enumerate(labels):
            tk.Label(win, text=label, font=("Microsoft YaHei", 11), bg="#1e1e2e", fg="#cdd6f4").place(x=30, y=30 + i * 60)
            entry = tk.Entry(win, font=("Consolas", 12), width=20, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
            entry.place(x=120, y=30 + i * 60)
            if key == "balance":
                entry.insert(0, "1000")
            fields[key] = entry
            
        def save():
            phone = fields["phone"].get().strip()
            password = fields["password"].get().strip()
            balance = fields["balance"].get().strip()
            
            if not phone or not password:
                messagebox.showwarning("提示", "手机号和密码不能为空")
                return
                
            try:
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO merchant (phone, password_hash, balance, status) VALUES (%s, %s, %s, 1)",
                    (phone, hash_password(password), float(balance))
                )
                win.destroy()
                self.show_table("merchant")
                messagebox.showinfo("成功", f"商户 {phone} 创建成功！\n初始余额：{balance}")
            except Exception as e:
                messagebox.showerror("错误", str(e))
                
        tk.Button(win, text="✅ 确认创建", font=("Microsoft YaHei", 11, "bold"),
                  bg="#a6e3a1", fg="#1e1e2e", relief="flat", padx=20, pady=6,
                  cursor="hand2", command=save).place(x=100, y=220)
                  
    def edit_balance(self):
        """修改余额"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一行")
            return
            
        values = self.tree.item(sel[0])["values"]
        if self.current_table != "merchant":
            messagebox.showinfo("提示", "请先切换到商户表")
            return
            
        row_id = values[0]
        id_col = self.columns.index("id")
        phone_col = self.columns.index("phone") if "phone" in self.columns else 1
        balance_col = self.columns.index("balance") if "balance" in self.columns else 3
        
        current_balance = values[balance_col]
        phone = values[phone_col]
        
        new_balance = simpledialog.askstring(
            "修改余额",
            f"商户：{phone}\n当前余额：{current_balance}\n\n输入新余额：",
            parent=self.root
        )
        
        if new_balance is not None:
            try:
                cur = self.conn.cursor()
                cur.execute("UPDATE merchant SET balance = %s WHERE id = %s", (float(new_balance), row_id))
                self.refresh_data()
                messagebox.showinfo("成功", f"商户 {phone} 余额已更新为 {new_balance}")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def reset_password(self):
        """重置商户登录密码"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一行")
            return

        if self.current_table != "merchant":
            messagebox.showinfo("提示", "请先切换到商户表")
            return

        values = self.tree.item(sel[0])["values"]
        row_id = values[0]
        phone_col = self.columns.index("phone") if "phone" in self.columns else 1
        phone = values[phone_col]

        new_password = simpledialog.askstring(
            "重置密码",
            f"商户：{phone}\n\n输入新登录密码：",
            parent=self.root,
            show="*"
        )

        if new_password is not None:
            new_password = new_password.strip()
            if not new_password:
                messagebox.showwarning("提示", "密码不能为空")
                return
            try:
                cur = self.conn.cursor()
                cur.execute("UPDATE merchant SET password_hash = %s WHERE id = %s", (hash_password(new_password), row_id))
                cur.close()
                self.refresh_data()
                messagebox.showinfo("成功", f"商户 {phone} 密码已重置")
            except Exception as e:
                messagebox.showerror("错误", str(e))
                
    def delete_row(self):
        """删除选中行"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一行")
            return
            
        values = self.tree.item(sel[0])["values"]
        row_id = values[0]
        
        if messagebox.askyesno("确认删除", f"确定要删除 ID={row_id} 的记录吗？\n此操作不可撤销！"):
            try:
                cur = self.conn.cursor()
                cur.execute(f"DELETE FROM {self.current_table} WHERE id = %s", (row_id,))
                self.refresh_data()
                messagebox.showinfo("成功", "删除成功")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def add_admin(self):
        """新增管理员"""
        win = tk.Toplevel(self.root)
        win.title("新增管理员")
        win.geometry("350x240")
        win.configure(bg="#1e1e2e")
        win.grab_set()
        
        fields = {}
        labels = [("账号", "username"), ("密码", "password")]
        
        for i, (label, key) in enumerate(labels):
            tk.Label(win, text=label, font=("Microsoft YaHei", 11), bg="#1e1e2e", fg="#cdd6f4").place(x=30, y=30 + i * 60)
            entry = tk.Entry(win, font=("Consolas", 12), width=20, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief="flat")
            entry.place(x=120, y=30 + i * 60)
            fields[key] = entry
            
        def save():
            username = fields["username"].get().strip()
            password = fields["password"].get().strip()
            
            if not username or not password:
                messagebox.showwarning("提示", "账号和密码不能为空")
                return
                
            try:
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO admin_user (username, password, role) VALUES (%s, %s, 'admin')",
                    (username, hash_password(password))
                )
                win.destroy()
                self.show_table("admin_user")
                messagebox.showinfo("成功", f"管理员 {username} 创建成功！")
            except Exception as e:
                messagebox.showerror("错误", str(e))
                
        tk.Button(win, text="✅ 确认创建", font=("Microsoft YaHei", 11, "bold"),
                  bg="#89b4fa", fg="#1e1e2e", relief="flat", padx=20, pady=6,
                  cursor="hand2", command=save).place(x=100, y=180)

if __name__ == "__main__":
    root = tk.Tk()
    app = DatabaseManager(root)
    root.mainloop()
