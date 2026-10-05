from tkinter import messagebox, ttk

from configs.user_config import UserConfig
from gui.user_editor import UserEditor
from storage.user_repository import UserRepository


class UserListView(ttk.LabelFrame):
    def __init__(self, parent, repo: UserRepository):
        super().__init__(parent, text="Юзеры", padding=4)
        self.repo = repo
        self.users_by_iid: dict[str, UserConfig] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        buttons = (
            ("Добавить", self.add_user),
            ("Изменить", self.edit_user),
            ("Удалить", self.delete_user),
            ("Вкл/Выкл", self.toggle_user),
        )
        for text, command in buttons:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)

        columns = ("enable", "name", "driver", "issue", "user_id", "activity_id", "comment")
        headings = {
            "enable": ("Вкл", 50),
            "name": ("Имя", 140),
            "driver": ("Driver", 90),
            "issue": ("Issue", 80),
            "user_id": ("user_id", 80),
            "activity_id": ("activity_id", 90),
            "comment": ("Комментарий", 180),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=6)
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.edit_user())
        self.tree.bind("<space>", self._on_space)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.users_by_iid.clear()
        for user in self.repo.list_users():
            iid = self.tree.insert(
                "",
                "end",
                values=(
                    "☑" if user.is_enable else "☐",
                    user.name,
                    user.driver,
                    user.issue_id,
                    user.user_id,
                    user.activity_id,
                    user.comment,
                ),
            )
            self.users_by_iid[iid] = user

    def selected_user(self) -> UserConfig | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Fill Redmine", "Выберите юзера", parent=self)
            return None
        return self.users_by_iid[selection[0]]

    def users_for_action(self, only_enabled: bool) -> list[UserConfig]:
        users = self.repo.list_users()
        if only_enabled:
            return [user for user in users if user.is_enable]
        selected = [self.users_by_iid[iid] for iid in self.tree.selection()]
        return selected or users

    def add_user(self) -> None:
        editor = UserEditor(self, None)
        self.wait_window(editor)
        if editor.result:
            self.repo.add_user(editor.result)
            self.refresh()

    def edit_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        editor = UserEditor(self, user)
        self.wait_window(editor)
        if editor.result:
            self.repo.update_user(user.db_id, editor.result)
            self.refresh()

    def delete_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        if messagebox.askyesno("Fill Redmine", f"Удалить юзера «{user.name}»?", parent=self):
            self.repo.delete_user(user.db_id)
            self.refresh()

    def toggle_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        self.repo.set_enabled(user.db_id, not user.is_enable)
        self.refresh()

    def _on_space(self, event) -> None:
        if not self.tree.selection():
            return
        self.toggle_user()
