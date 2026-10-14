# -*- coding: utf-8 -*-
"""
PyMifareTool - 本地发卡管理与刷卡流水 SQLite 数据库
"""

import sqlite3
import os
import datetime
from typing import List, Dict, Optional, Any

class CardDatabase:
    def __init__(self, db_path: str = "cards.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                uid TEXT PRIMARY KEY,
                card_name TEXT DEFAULT '未命名卡片',
                card_holder TEXT DEFAULT '默认访客',
                card_type TEXT DEFAULT 'Mifare Classic 1K',
                dec_10d TEXT,
                wiegand_26 TEXT,
                note TEXT,
                created_at TIMESTAMP,
                last_swiped_at TIMESTAMP,
                swipe_count INTEGER DEFAULT 1
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS swipe_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT,
                swiped_at TIMESTAMP,
                raw_hex TEXT
            )
        """)

        conn.commit()
        conn.close()

    def record_swipe(self, uid: str, conv_info: Dict[str, str], raw_hex: str) -> Dict[str, Any]:
        """记录一次刷卡事件并更新卡片基本信息"""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        c = conn.cursor()

        # 写入刷卡流水
        c.execute(
            "INSERT INTO swipe_logs (uid, swiped_at, raw_hex) VALUES (?, ?, ?)",
            (uid, now_str, raw_hex)
        )

        # 检查是否已存在此卡
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
                INSERT INTO cards (uid, card_name, card_holder, card_type, dec_10d, wiegand_26, created_at, last_swiped_at, swipe_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uid,
                "未命名卡片",
                "默认访客",
                conv_info.get("card_type") or conv_info.get("uid_type", "Mifare Classic 1K"),
                conv_info.get("dec_10d_rev", ""),
                conv_info.get("wiegand_26", ""),
                now_str,
                now_str,
                1
            ))

        conn.commit()
        conn.close()

        return {"uid": uid, "swipe_count": count, "time": now_str}

    def update_card_info(self, uid: str, name: str, holder: str, note: str):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE cards SET card_name = ?, card_holder = ?, note = ? WHERE uid = ?",
            (name, holder, note, uid)
        )
        conn.commit()
        conn.close()

    def get_card(self, uid: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT uid, card_name, card_holder, card_type, dec_10d, wiegand_26, note, created_at, last_swiped_at, swipe_count FROM cards WHERE uid = ?", (uid,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "uid": row[0],
                "card_name": row[1],
                "card_holder": row[2],
                "card_type": row[3],
                "dec_10d": row[4],
                "wiegand_26": row[5],
                "note": row[6],
                "created_at": row[7],
                "last_swiped_at": row[8],
                "swipe_count": row[9],
            }
        return None

    def list_all_cards(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT uid, card_name, card_holder, card_type, dec_10d, wiegand_26, note, created_at, last_swiped_at, swipe_count FROM cards ORDER BY last_swiped_at DESC")
        rows = c.fetchall()
        conn.close()
        cards = []
        for r in rows:
            cards.append({
                "uid": r[0], "card_name": r[1], "card_holder": r[2], "card_type": r[3],
                "dec_10d": r[4], "wiegand_26": r[5], "note": r[6], "created_at": r[7],
                "last_swiped_at": r[8], "swipe_count": r[9]
            })
        return cards

    def list_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT l.id, l.uid, l.swiped_at, l.raw_hex, c.card_name, c.card_holder
            FROM swipe_logs l
            LEFT JOIN cards c ON l.uid = c.uid
            ORDER BY l.id DESC LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        logs = []
        for r in rows:
            logs.append({
                "id": r[0], "uid": r[1], "swiped_at": r[2], "raw_hex": r[3],
                "card_name": r[4], "card_holder": r[5]
            })
        return logs

    def clear_swipe_logs(self) -> int:
        """清空 swipe_logs 数据表所有记录并返回被删除的条数"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM swipe_logs")
        count = c.fetchone()[0]
        c.execute("DELETE FROM swipe_logs")
        try:
            c.execute("DELETE FROM sqlite_sequence WHERE name='swipe_logs'")
        except Exception:
            pass
        conn.commit()
        conn.close()
        return count

    def delete_single_log(self, log_id: int) -> bool:
        """删除单条指定的流水记录"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM swipe_logs WHERE id = ?", (log_id,))
        affected = c.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def close(self):
        pass
