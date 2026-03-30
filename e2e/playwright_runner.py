"""
Playwright 実行エンジン

Playwright の同期 API を使用して、フロントエンドを操作する。
ページナビゲーション・フォーム操作・スクリーンショット取得などを提供する。
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

from config import get_config


@dataclass
class BrowserAction:
    """ブラウザ操作の記録"""
    step_no: int            # ステップ番号
    action_type: str        # "navigate" | "click" | "fill" | "screenshot" など
    target: str             # 操作対象（URLまたはセレクター）
    value: str = ""         # 入力値（fillアクションの場合）
    success: bool = True    # 成功/失敗
    error_message: str = "" # エラーメッセージ
    screenshot_path: str = ""  # スクリーンショットのパス


@dataclass
class PageContext:
    """現在のページコンテキスト"""
    url: str                # 現在のURL
    title: str              # ページタイトル
    visible_text: str       # 可視テキスト（エラー検出用）
    html_snapshot: str = "" # HTML スナップショット（デバッグ用）


class PlaywrightRunner:
    """
    Playwright を使ってフロントエンドを操作するクラス。

    同期 API を使用し、以下の操作をサポートする:
    - ページナビゲーション
    - フォーム入力・送信
    - テーブルデータ検証
    - スクリーンショット取得
    - ログイン状態の管理
    """

    # Next.js のルーティングパス定義
    KNOWN_ROUTES = {
        "hotel_list": "/hotels",
        "hotel_new": "/hotels/new",
        "booking_list": "/booking",
        "room_list": "/room",
        "plan_list": "/plans",
        "customer_list": "/customer",
        "coupon_list": "/coupon",
        "facility_list": "/facility",
        "parking_lot_list": "/parking-lot",
        "rental_car_list": "/rental-car",
        "account": "/account",
        "contract": "/contract",
        "login": "/login",
    }

    def __init__(self):
        self._config = get_config()
        self._browser = None
        self._page = None
        self._is_logged_in = False
        self._actions: list[BrowserAction] = []

    def start(self) -> None:
        """ブラウザを起動する"""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._config.e2e_headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = self._browser.new_context(
            base_url=self._config.e2e_base_url,
            viewport={"width": 1280, "height": 720},
            locale="ja-JP",
        )
        self._page = context.new_page()

        # タイムアウト設定
        self._page.set_default_timeout(self._config.e2e_timeout_ms)
        self._page.set_default_navigation_timeout(self._config.e2e_timeout_ms)

    def stop(self) -> None:
        """ブラウザを終了する"""
        try:
            if self._browser:
                self._browser.close()
            if hasattr(self, "_playwright"):
                self._playwright.stop()
        except Exception:
            pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def login(self, email: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        対象アプリケーションにログインする。

        Args:
            email: メールアドレス（省略時は設定値を使用）
            password: パスワード（省略時は設定値を使用）

        Returns:
            bool: ログイン成功かどうか
        """
        email = email or self._config.e2e_test_email
        password = password or self._config.e2e_test_password

        try:
            self._navigate("/login")

            # メールアドレス入力
            self._page.fill('input[type="email"], input[name="email"]', email)

            # パスワード入力
            self._page.fill('input[type="password"], input[name="password"]', password)

            # ログインボタンクリック
            self._page.click(
                'button[type="submit"], button:has-text("ログイン"), button:has-text("Login")'
            )

            # ダッシュボードへのリダイレクト待機
            self._page.wait_for_url(
                lambda url: "/login" not in url,
                timeout=10000
            )

            self._is_logged_in = True
            self._record_action(0, "login", "/login", f"{email}", success=True)
            return True

        except Exception as e:
            self._record_action(0, "login", "/login", "", success=False, error=str(e))
            return False

    def navigate(self, url_or_route: str, step_no: int = 0) -> bool:
        """
        指定URLまたはルート名に遷移する。

        Args:
            url_or_route: URLパス（/hotels）またはルート名（hotel_list）
            step_no: ステップ番号

        Returns:
            bool: 遷移成功かどうか
        """
        # ルート名→URLの変換
        if not url_or_route.startswith("/"):
            url_or_route = self.KNOWN_ROUTES.get(url_or_route, "/" + url_or_route)

        return self._navigate(url_or_route, step_no)

    def _navigate(self, path: str, step_no: int = 0) -> bool:
        """内部ナビゲーション処理"""
        try:
            self._page.goto(path)
            # ページロード完了待機（Next.jsのhydrationを考慮）
            self._page.wait_for_load_state("networkidle")
            self._record_action(step_no, "navigate", path, success=True)
            return True
        except Exception as e:
            self._record_action(step_no, "navigate", path, success=False, error=str(e))
            return False

    def click(self, selector: str, step_no: int = 0) -> bool:
        """
        要素をクリックする。

        複数のセレクターを試行して最初に見つかった要素をクリックする。

        Args:
            selector: CSSセレクターまたはテキスト
            step_no: ステップ番号

        Returns:
            bool: クリック成功かどうか
        """
        # テキストによる検索も試みる
        selectors = [
            selector,
            f'button:has-text("{selector}")',
            f'a:has-text("{selector}")',
            f'[data-testid="{selector}"]',
        ]

        for sel in selectors:
            try:
                self._page.click(sel, timeout=5000)
                self._record_action(step_no, "click", sel, success=True)
                return True
            except Exception:
                continue

        self._record_action(step_no, "click", selector, success=False, error="要素が見つかりません")
        return False

    def fill_form(self, selector: str, value: str, step_no: int = 0) -> bool:
        """
        フォームフィールドに入力する。

        Args:
            selector: 入力フィールドのセレクター
            value: 入力値
            step_no: ステップ番号

        Returns:
            bool: 入力成功かどうか
        """
        try:
            self._page.fill(selector, value)
            self._record_action(step_no, "fill", selector, value, success=True)
            return True
        except Exception as e:
            self._record_action(step_no, "fill", selector, value, success=False, error=str(e))
            return False

    def get_page_context(self) -> PageContext:
        """
        現在のページのコンテキスト情報を取得する。

        エラー検出やデバッグに使用する。
        """
        try:
            url = self._page.url
            title = self._page.title()
            visible_text = self._page.inner_text("body")[:2000]  # 最大2000文字
            return PageContext(
                url=url,
                title=title,
                visible_text=visible_text,
            )
        except Exception as e:
            return PageContext(
                url=self._page.url if self._page else "",
                title="",
                visible_text=f"エラー: {e}",
            )

    def take_screenshot(self, name: str, step_no: int = 0) -> str:
        """
        スクリーンショットを保存する。

        Args:
            name: ファイル名（拡張子なし）
            step_no: ステップ番号

        Returns:
            str: 保存されたファイルパス
        """
        screenshot_dir = Path(self._config.e2e_screenshot_dir)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        file_path = screenshot_dir / f"{name}_{timestamp}.png"

        try:
            self._page.screenshot(path=str(file_path), full_page=True)
            self._record_action(
                step_no, "screenshot", str(file_path), success=True
            )
            return str(file_path)
        except Exception as e:
            self._record_action(
                step_no, "screenshot", name, success=False, error=str(e)
            )
            return ""

    def wait_for_selector(self, selector: str, timeout: int = 5000) -> bool:
        """指定セレクターが表示されるまで待機する"""
        try:
            self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    def get_table_data(self) -> list[dict[str, str]]:
        """
        現在のページに存在するテーブルデータを取得する。

        Next.js のデータテーブル（TanStack Table など）を想定。
        """
        try:
            rows = self._page.query_selector_all("tbody tr")
            if not rows:
                return []

            # ヘッダー取得
            headers = [
                th.inner_text()
                for th in self._page.query_selector_all("thead th")
            ]

            table_data = []
            for row in rows[:100]:  # 最大100行
                cells = row.query_selector_all("td")
                row_data = {}
                for i, cell in enumerate(cells):
                    key = headers[i] if i < len(headers) else f"col_{i}"
                    row_data[key] = cell.inner_text()
                table_data.append(row_data)

            return table_data
        except Exception:
            return []

    def check_error_state(self) -> Optional[str]:
        """
        エラー状態を検出する。

        よくあるエラーパターン:
        - 404 ページ
        - 認証エラー
        - バリデーションエラー
        - APIエラー

        Returns:
            str | None: エラーメッセージ（エラーがない場合はNone）
        """
        try:
            # 404 Not Found
            if "404" in self._page.title() or "Not Found" in self._page.title():
                return "404 Not Found エラー"

            # ログインページへのリダイレクト（認証エラー）
            if "/login" in self._page.url and not self._is_logged_in:
                return "認証エラー: ログインページにリダイレクトされました"

            # エラーメッセージ要素の検索
            error_selectors = [
                "[role='alert']",
                ".error-message",
                ".alert-danger",
                "[data-testid='error']",
            ]
            for sel in error_selectors:
                error_el = self._page.query_selector(sel)
                if error_el:
                    return f"エラーメッセージ: {error_el.inner_text()}"

            # レスポンスエラー（Next.js のエラーページ）
            page_text = self._page.inner_text("body")
            if "Application error" in page_text or "500" in self._page.title():
                return "アプリケーションエラー（500）"

            return None

        except Exception as e:
            return f"エラー検出中に例外: {e}"

    def _record_action(
        self,
        step_no: int,
        action_type: str,
        target: str,
        value: str = "",
        success: bool = True,
        error: str = "",
    ) -> None:
        """操作を記録する"""
        self._actions.append(BrowserAction(
            step_no=step_no,
            action_type=action_type,
            target=target,
            value=value,
            success=success,
            error_message=error,
        ))

    @property
    def actions(self) -> list[BrowserAction]:
        """実行した操作の記録を返す"""
        return self._actions.copy()

    def clear_actions(self) -> None:
        """操作記録をクリアする"""
        self._actions.clear()
