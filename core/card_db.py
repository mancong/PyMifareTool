# -*- coding: utf-8 -*-
"""
PyMifareTool - 本地发卡管理与刷卡流水 SQLite 数据库
"""

import os
import sqlite3
import datetime
import threading
from contextlib import contextmanager
from typing import List, Dict, Optional, Any


class CardDatabase:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "cards.db")

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = os.path.abspath(db_path) if db_path else self.DEFAULT_DB_PATH
        self._local = threading.local()
        self._connections = set()
        self._connections_lock = threading.Lock()
        self._closed = False
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._closed:
            raise sqlite3.ProgrammingError("CardDatabase 已关闭")
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._local.conn = conn
            with self._connections_lock:
                self._connections.add(conn)
        return conn

    @contextmanager
    def _cursor(self, write: bool = False):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield cursor
            if write:
                conn.commit()
        except Exception:
            if write:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            cursor.close()

    def _init_db(self):
        with self._cursor(write=True) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS cards (
                    uid TEXT PRIMARY KEY,
                    card_name TEXT DEFAULT '未命名卡片',
                    card_holder TEXT DEFAULT '默认访客',
                    card_type TEXT DEFAULT 'Mifare Classic 1K',
                    dec_10d TEXT,
                    wiegand_26 TEXT,
                    wiegand_34 TEXT,
                    note TEXT,
                    created_at TIMESTAMP,
                    last_swiped_at TIMESTAMP,
                    swipe_count INTEGER DEFAULT 1
                )
            """)

            # 自动迁移检查，保证向后兼容老数据库
            c.execute("PRAGMA table_info(cards)")
            existing_cols = [row[1] for row in c.fetchall()]
            if "wiegand_34" not in existing_cols:
                try:
                    c.execute("ALTER TABLE cards ADD COLUMN wiegand_34 TEXT")
                except Exception:
                    pass

            c.execute("""
                CREATE TABLE IF NOT EXISTS swipe_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT,
                    swiped_at TIMESTAMP,
                    raw_hex TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS card_keys (
                    uid TEXT,
                    sector INTEGER,
                    key_a TEXT DEFAULT '',
                    key_b TEXT DEFAULT '',
                    updated_at TIMESTAMP,
                    PRIMARY KEY (uid, sector)
                )
            """)

    def record_swipe(self, uid: str, conv_info: Dict[str, str], raw_hex: str) -> Dict[str, Any]:
        """记录一次刷卡事件并更新卡片基本信息"""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cursor(write=True) as c:
            c.execute(
                "INSERT INTO swipe_logs (uid, swiped_at, raw_hex) VALUES (?, ?, ?)",
                (uid, now_str, raw_hex)
            )

            c.execute("SELECT swipe_count FROM cards WHERE uid = ?", (uid,))
            row = c.fetchone()
            if row:
                count = row[0] + 1
                c.execute(
                    "UPDATE cards SET last_swiped_at = ?, swipe_count = ? WHERE uid = ?",
                    (now_str, count, uid)
                )
            else:
                count = 1
                c.execute("""
                    INSERT INTO cards (uid, card_name, card_holder, card_type, dec_10d, wiegand_26, wiegand_34, created_at, last_swiped_at, swipe_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    uid,
                    "未命名卡片",
                    "默认访客",
                    conv_info.get("card_type") or conv_info.get("uid_type", "Mifare Classic 1K"),
                    conv_info.get("dec_10d_rev", ""),
                    conv_info.get("wiegand_26", ""),
                    conv_info.get("wiegand_34", ""),
                    now_str,
                    now_str,
                    1
                ))

        return {"uid": uid, "swipe_count": count, "time": now_str}

    def update_card_info(self, uid: str, name: str, holder: str, note: str):
        with self._cursor(write=True) as c:
            c.execute(
                "UPDATE cards SET card_name = ?, card_holder = ?, note = ? WHERE uid = ?",
                (name, holder, note, uid)
            )

    def get_card(self, uid: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as c:
            c.execute("SELECT uid, card_name, card_holder, card_type, dec_10d, wiegand_26, wiegand_34, note, created_at, last_swiped_at, swipe_count FROM cards WHERE uid = ?", (uid,))
            row = c.fetchone()
        if row:
            return {
                "uid": row[0],
                "card_name": row[1],
                "card_holder": row[2],
                "card_type": row[3],
                "dec_10d": row[4],
                "wiegand_26": row[5],
                "wiegand_34": row[6],
                "note": row[7],
                "created_at": row[8],
                "last_swiped_at": row[9],
                "swipe_count": row[10],
            }
        return None

    def list_all_cards(self) -> List[Dict[str, Any]]:
        with self._cursor() as c:
            c.execute("SELECT uid, card_name, card_holder, card_type, dec_10d, wiegand_26, wiegand_34, note, created_at, last_swiped_at, swipe_count FROM cards ORDER BY last_swiped_at DESC")
            rows = c.fetchall()
        return [{
            "uid": r[0], "card_name": r[1], "card_holder": r[2], "card_type": r[3],
            "dec_10d": r[4], "wiegand_26": r[5], "wiegand_34": r[6], "note": r[7], "created_at": r[8],
            "last_swiped_at": r[9], "swipe_count": r[10]
        } for r in rows]

    def list_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._cursor() as c:
            c.execute("""
                SELECT l.id, l.uid, l.swiped_at, l.raw_hex, c.card_name, c.card_holder
                FROM swipe_logs l
                LEFT JOIN cards c ON l.uid = c.uid
                ORDER BY l.id DESC LIMIT ?
            """, (limit,))
            rows = c.fetchall()
        return [{
            "id": r[0], "uid": r[1], "swiped_at": r[2], "raw_hex": r[3],
            "card_name": r[4], "card_holder": r[5]
        } for r in rows]

    def clear_swipe_logs(self) -> int:
        """清空 swipe_logs 数据表所有记录并返回被删除的条数"""
        with self._cursor(write=True) as c:
            c.execute("SELECT COUNT(*) FROM swipe_logs")
            count = c.fetchone()[0]
            c.execute("DELETE FROM swipe_logs")
            try:
                c.execute("DELETE FROM sqlite_sequence WHERE name='swipe_logs'")
            except Exception:
                pass
        return count

    def delete_single_log(self, log_id: int) -> bool:
        """删除单条指定的流水记录"""
        with self._cursor(write=True) as c:
            c.execute("DELETE FROM swipe_logs WHERE id = ?", (log_id,))
            affected = c.rowcount
        return affected > 0

    # ─────────────────────────────────────────────────────────────
    # 卡片扇区密钥留存 (读取/破解成功后持久化，便于后续直接解密)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _norm_key(val: Optional[str]) -> str:
        """规范化密钥字符串: 过滤占位词/空白并统一大写"""
        if not val:
            return ""
        s = str(val).strip().upper().replace(" ", "")
        if s in ("未破解", "未解密", "未知", "NONE", "NULL"):
            return ""
        return s

    def save_sector_keys(self, uid: str, sector: int,
                         key_a: Optional[str] = None, key_b: Optional[str] = None) -> None:
        """保存/更新指定卡号某扇区的密钥 (仅覆盖非空密钥, 保留既有值)"""
        if not uid:
            return
        ka = self._norm_key(key_a)
        kb = self._norm_key(key_b)
        if not ka and not kb:
            return
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._cursor(write=True) as c:
            c.execute("""
                INSERT INTO card_keys (uid, sector, key_a, key_b, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(uid, sector) DO UPDATE SET
                    key_a = CASE WHEN excluded.key_a != '' THEN excluded.key_a ELSE card_keys.key_a END,
                    key_b = CASE WHEN excluded.key_b != '' THEN excluded.key_b ELSE card_keys.key_b END,
                    updated_at = excluded.updated_at
            """, (uid, int(sector), ka, kb, now_str))

    def save_card_keys(self, uid: str, keys: Dict[int, Dict[str, str]]) -> int:
        """批量保存一张卡多个扇区的密钥, 返回处理的扇区数"""
        n = 0
        for sector, kv in (keys or {}).items():
            if not isinstance(kv, dict):
                continue
            self.save_sector_keys(uid, int(sector), kv.get("key_a"), kv.get("key_b"))
            n += 1
        return n

    def get_card_keys(self, uid: str) -> Dict[int, Dict[str, str]]:
        """读取指定卡号已留存的扇区密钥 {sector: {key_a, key_b}}"""
        with self._cursor() as c:
            c.execute("SELECT sector, key_a, key_b FROM card_keys WHERE uid = ? ORDER BY sector", (uid,))
            rows = c.fetchall()
        return {int(r[0]): {"key_a": r[1] or "", "key_b": r[2] or ""} for r in rows}

    def list_all_card_keys(self) -> List[Dict[str, Any]]:
        """列出全部已留存的卡号-扇区密钥记录"""
        with self._cursor() as c:
            c.execute("SELECT uid, sector, key_a, key_b, updated_at FROM card_keys ORDER BY uid, sector")
            rows = c.fetchall()
        return [{"uid": r[0], "sector": r[1], "key_a": r[2], "key_b": r[3], "updated_at": r[4]}
                for r in rows]

    def clear_card_keys(self) -> int:
        """清空密钥留存表并返回被删除条数"""
        with self._cursor(write=True) as c:
            c.execute("SELECT COUNT(*) FROM card_keys")
            count = c.fetchone()[0]
            c.execute("DELETE FROM card_keys")
        return count

    def close(self):
        """关闭所有线程创建的连接并标记数据库为已关闭。"""
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
        for conn in connections:
            try:
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        self._closed = True
        self._local = threading.local()
