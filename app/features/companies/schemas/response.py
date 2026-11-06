from typing import Optional

from pydantic import BaseModel


class CompanyAccountOptionOut(BaseModel):
    id: int
    name: Optional[str]
