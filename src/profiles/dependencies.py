from src.config import settings
from src.security import RateLimiter, limit_by_ip

media_upload_limiter = RateLimiter(
    limit=settings.media_uploads_per_ip_per_hour, window_seconds=3600
)
limit_media_uploads = limit_by_ip(media_upload_limiter)
