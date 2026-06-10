import uvicorn

from api.config import get_host, get_port


if __name__ == "__main__":
    uvicorn.run("api.main:app", host=get_host(), port=get_port())
