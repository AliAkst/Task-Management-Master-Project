import json
from datetime import date, datetime
from typing import Any

from redis.asyncio import Redis, from_url

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# --- CUSTOM JSON ENCODER ---
class DateTimeEncoder(json.JSONEncoder):
    """
    datetime ve date objelerini JSON'A serialize edebilen encoder.

    Kullanim:
        json.dumps(data,cls=DateTimeEncoder)
    """
    def default(self, obj):
        if isinstance(obj,datetime):
            return obj.isoformat()
        if isinstance(obj,date):
            return obj.isoformat
        return super().default(obj)

class RedisCache:
    """Cache islemlerini yonetmek icin olusturulan class"""
    def __init__(self):
        self.redis : Redis | None = None

    async def connect(self):
        """Redis'e asenkron baglanti kurar."""
        try:
            redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            if settings.redis_password:
                redis_url=f"redis://{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            self.redis = from_url(redis_url,encoding="utf-8",decode_responses= True)

            #Baglanti testi
            await self.redis.ping()
            logger.info(f"Connected to Redis at {settings.redis_host}:{settings.redis_port}")
        except Exception as e:
            logger.error(f"Redis Connection Error: {e}")
            self.redis = None

    async def disconnect(self):
        """Redis baglantisini guvenli bir sekilde kapatir."""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected From Redis")
    
    async def get(self, key : str)-> Any | None :
        """Cache'den veri alir ve JSON'dan Python objesine donusturur."""
        if not self.redis:
            return None
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(self, key:str, value:Any, ttl:int | None = None):
        """Veriyi JSON'a cevirir ve belirtilen sureyle (TTL) Redis'e kaydeder."""
        if not self.redis:
            return
        
        try:
            # Eger TTL verilmediyse configdeki varsayilani kullan
            expiration = ttl or settings.cache_ttl_seconds

            
            json_value = json.dumps(value, cls=DateTimeEncoder)
            await self.redis.set(key, json_value, ex = expiration)
            logger.debug(f"Cached key: {key} (TTL={expiration}s)")
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")

    async def delete(self, key: str):
        """Tek bir key'i siler"""
        if not self.redis:
            return
        try:
            await self.redis.delete(key)
            logger.debug(f"Deleted cache key: {key}")
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key} : {e}")

    async def delete_pattern(self, pattern: str):
        """Pattern'e uyan tum anahtarlari siler(invalidation icin gerekli)"""
        if not self.redis:
            return
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.debug(f"Deleted{len(keys)} keys with pattern: {pattern}")
        except Exception as e:
            logger.error(f"Redis DELETE PATTERN error for {pattern}:{e}")

redis_cache = RedisCache()