from app.core.cache import redis_cache
from app.core.logging import get_logger
import time
from app.config import settings
logger = get_logger(__name__)

class RateLimiter:
    """
    Token Bucket algoritmasi kullanilarak rate limiting yapar.
    
    Calisma mantigi:
    1-Her kullanicinin bir bucket'i olur.(Rediste)
    2-Kova maksimum N token alir.
    3-Her istek 1 token harcar.
    4-her saniye kova yavasca dolar.
    5-Kova bos ise -> 429 To Many Requests doner.
    
    Redis Key Formati:
        ratelimit::{identifier}

    Redis value(JSON):
        {"tokens":95.5,"last_update":1706012345.123}
    """
    def __init__(
        self,
        max_requests:int | None = None,
        window_seconds:int | None = None
    ):
        """
        Docstring for __init__
        
        Args:
            max_requests = Maksimum token sayisi(default : config'den)
            window_seconds: Token yenileme suresi (default : config'den)
        """
        self.max_requests = max_requests or settings.rate_limiting_requests
        self.window_seconds = window_seconds or settings.rate_limit_window_seconds

        #Token yenileme hizi = max_requests/window_seconds
        #ornek:100 token/ 60 saniye = 1.67 token/saniye
        self.refill_rate = self.max_requests/self.window_seconds
    
    def _get_key(self,identifier: str) -> str:
        """
        Docstring for _get_key
        Rate limit key'i olusturur.

        Args:
            identifier: Kullanici ip ya da id adresi
        Returns:
            Redis Key: "ratelimit:{identifier}"
        """
        return f"ratelimit:{identifier}"
    async def is_allowed(self, identifier:str) -> tuple[bool, dict]:
        """
        Istegin rate limit'e takilip takilmadigini kontrol eder.

        Token Bucket algoritmasi:
        1-Mevcut token sayisini al.
        2-Son guncellemeden bu yana gecen sureye gore token ekle.
        3-Token >= 1 ise: izin ver,1 token dus
        4-Token < 1 ise: Reddet
        
        Args:
            identifier: Kullanici ip ya da id adresi
        Returns:
            tuple[bool,dict]: (izin_var_mi, bilgi_dict)

            bilgi_dict ingredients:
            -allowed:bool
            -remaining: int (kalan token)
            -reset_after: float(saniye, token dolmasina kalan sure)
            -limit: int(maksimum token)
        """
        key = self._get_key(identifier)
        now = time.time()

        # Redisten mevcut durum aliyoruz.
        data = await redis_cache.get(key)

        if data is None:
            #ilk istek atilir(kova dolu baslar.)
            tokens = self.max_requests
            last_update = now
        else:
            tokens = data["tokens"]
            last_update = data["last_update"]
        
        # Gecen sureye gore token ekle (refill)
        time_passed = now - last_update
        tokens = min(
            self.max_requests, #maksimumu gecemez.
            tokens + (time_passed * self.refill_rate)
        )

        # Token kontrolu
        if tokens >= 1:
            tokens -= 1
            allowed = True
        else:
            allowed = False
        
        # Guncel Durumu Redis'e kaydet
        await redis_cache.set(
            key,
            {"tokens" : tokens, "last_update" : now},
            ttl= self.window_seconds * 2
        )
        
        # Bilgi dict'i hazirla.
        reset_after = (1-tokens) / self.refill_rate if tokens < 1 else 0

        info = {
            "allowed":allowed,
            "remaining": max(0, int(tokens)),
            "reset_after":round(reset_after,2),
            "limit": self.max_requests
        }

        if not allowed:
            logger.warning(f"Rate Limit exceeded for {identifier}")
        
        return allowed, info

rate_limiter = RateLimiter()