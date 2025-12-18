from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_active_user
from ..database import get_session
from ..models import SavingsProduct
from ..schemas import SavingsProductCreate, SavingsProductRead

router = APIRouter(prefix="/products", tags=["Savings Products"])

def _is_platform_admin(role: str) -> bool:
    return role in {"admin", "operator"}


@router.get("/", response_model=List[SavingsProductRead])
def list_products(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> List[SavingsProduct]:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    return session.exec(select(SavingsProduct)).all()


@router.post("/", response_model=SavingsProductRead, status_code=201)
def create_product(
    payload: SavingsProductCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> SavingsProduct:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    product = SavingsProduct(**payload.model_dump())
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


@router.get("/{product_id}", response_model=SavingsProductRead)
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> SavingsProduct:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    product = session.get(SavingsProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_active_user),
) -> None:
    if not _is_platform_admin(getattr(current_user, "role", "")):
        raise HTTPException(status_code=403, detail="Admins only")
    product = session.get(SavingsProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    session.delete(product)
    session.commit()
