from fastapi import FastAPI
from app.db import init_pool, close_pool
from app.proxy import proxy_router
from app.ux import ux_router

app = FastAPI(title="TokenProxy")

app.include_router(proxy_router)
app.include_router(ux_router)


@app.on_event("startup")
async def startup():
    await init_pool()


@app.on_event("shutdown")
async def shutdown():
    await close_pool()
