from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from typing import Optional, Dict, Any

from app.utils.misc_function import get_time_now
from sqlalchemy import cast, String
from app.database import models

class ActionHistoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def write_record(self, **kwargs):
        action_history = models.ActionHistory(**kwargs)
        self.session.add(action_history)
        await self.session.commit()
        await self.session.refresh(action_history)
        return action_history

    async def write_transfer_record(
        self,
        sender_id: int,
        receiver_id: int,
        amount: float,
        sender_ref: str,
        receiver_ref: str,
        chat_id: Optional[int] = None,
        additional_details: Optional[Dict[str, Any]] = None
    ) -> models.ActionHistory:
        """
        Создает запись о переводе с автоматической проверкой на подозрительность
        Записывает получателя в user_id для удобства получения истории полученных переводов
        """
        # Определяем подозрительность операции
        print(str(receiver_id) == str(sender_ref))
        print(receiver_id)
        print(sender_ref)
        is_same_ref = str(receiver_id) == str(sender_ref)
        suspicion_level = "high" if is_same_ref else "low"
        
        # Базовые детали перевода
        transfer_details = {
            "transfer_type": "user_to_user",
            "sender": {
                "user_id": sender_id,
                "ref": sender_ref
            },
            "receiver": {
                "user_id": receiver_id,
                "ref": receiver_ref
            },
            "amount": amount,
            "is_same_ref": is_same_ref,
            "suspicion_level": suspicion_level,
            "timestamp": get_time_now().isoformat()
        }
        
        # Добавляем дополнительные детали если есть
        if additional_details:
            transfer_details.update(additional_details)
        
        # Если операция подозрительная, проверяем частоту таких операций
        if is_same_ref:
            recent_suspicious_count = await self.get_recent_suspicious_transfers_count(
                sender_ref, hours=24
            )
            transfer_details["recent_suspicious_count"] = recent_suspicious_count
            
            # Повышаем уровень подозрительности при множественных операциях
            if recent_suspicious_count > 5:
                transfer_details["suspicion_level"] = "critical"
        
        # Создаем запись - В user_id записываем получателя!
        record_data = {
            "user_id": receiver_id,  # Получатель - для истории полученных переводов
            "chat_id": chat_id or receiver_id,
            "action_type": "money_transfer",
            "details": transfer_details
        }
        
        return await self.write_record(**record_data)

    async def get_recent_suspicious_transfers_count(
        self, 
        ref: str, 
        hours: int = 24
    ) -> int:
        """
        Возвращает количество подозрительных переводов для данного ref за указанный период
        """
        time_threshold = get_time_now() - timedelta(hours=hours)
        
        query = select(func.count()).where(
            and_(
                models.ActionHistory.action_type == "money_transfer",
                cast(models.ActionHistory.details["is_same_ref"], String) == "true",
                cast(models.ActionHistory.details["sender"]["ref"], String) == ref,
                models.ActionHistory.created_at >= time_threshold
            )
        )
        
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_suspicious_transfers(
        self,
        limit: int = 100,
        offset: int = 0,
        suspicion_level: Optional[str] = None
    ):
        """
        Получает список подозрительных переводов с фильтрацией по уровню подозрительности
        """
        conditions = [
            models.ActionHistory.action_type == "money_transfer",
            cast(models.ActionHistory.details["is_same_ref"], String) == "true"
        ]
        
        if suspicion_level:
            conditions.append(
                cast(models.ActionHistory.details["suspicion_level"], String) == suspicion_level
            )
        
        query = select(models.ActionHistory).where(
            and_(*conditions)
        ).order_by(
            models.ActionHistory.created_at.desc()
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_user_received_transfers(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ):
        """
        Получает все переводы, полученные конкретным пользователем
        """
        query = select(models.ActionHistory).where(
            and_(
                models.ActionHistory.user_id == user_id,  # Получатель
                models.ActionHistory.action_type == "money_transfer"
            )
        ).order_by(
            models.ActionHistory.created_at.desc()
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_user_received_transfers_count(
        self,
        user_id: int,
        hours: Optional[int] = None
    ) -> int:
        """
        Возвращает количество переводов, полученных пользователем
        """
        conditions = [
            models.ActionHistory.user_id == user_id,
            models.ActionHistory.action_type == "money_transfer"
        ]
        
        if hours:
            time_threshold = get_time_now() - timedelta(hours=hours)
            conditions.append(models.ActionHistory.created_at >= time_threshold)
        
        query = select(func.count()).where(and_(*conditions))
        
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_user_suspicious_received_transfers(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ):
        """
        Получает подозрительные переводы, полученные пользователем
        """
        query = select(models.ActionHistory).where(
            and_(
                models.ActionHistory.user_id == user_id,
                models.ActionHistory.action_type == "money_transfer",
                cast(models.ActionHistory.details["is_same_ref"], String) == "true"
            )
        ).order_by(
            models.ActionHistory.created_at.desc()
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_count_action_history_offsets(self, offset1: str, offset2: str, **kwargs):
        query = select(func.count()).select_from(models.ActionHistory)

        conditions = [
            models.ActionHistory.created_at > offset2,
            models.ActionHistory.created_at < offset1
        ]

        for key, value in kwargs.items():
            if hasattr(models.ActionHistory, key):
                conditions.append(getattr(models.ActionHistory, key) == value)

        query = query.where(*conditions)

        result = await self.session.execute(query)
        return result.scalar()