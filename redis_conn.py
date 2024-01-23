import redis
import os
from dotenv import load_dotenv

load_dotenv()

host = os.environ.get('REDIS_HOST')
redis_port = os.environ.get('REDIS_PORT')
redis_password = os.environ.get('REDIS_PASSWORD')

rport = int(redis_port)

r = redis.Redis(
  host=host,
  port=rport,
  password=redis_password,
  decode_responses=True
)
