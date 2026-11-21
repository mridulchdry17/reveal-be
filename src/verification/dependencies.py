from src.config import settings
from src.security import RateLimiter, limit_by_ip

upload_limiter = RateLimiter(
    limit=settings.verification_uploads_per_ip_per_hour, window_seconds=3600
)
limit_uploads = limit_by_ip(upload_limiter)
