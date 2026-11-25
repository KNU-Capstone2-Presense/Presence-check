from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

class SessionCreate(BaseModel):
    place_id: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')

class ImagePayload(BaseModel):
    mime_type: Literal['image/jpeg']
    data_base64: str = Field(min_length=1, max_length=6_000_000)

class AuthRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')
    type: Literal['auth_request']
    attempt_id: UUID
    student_id: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')
    session_id: str = Field(min_length=1, max_length=80)
    place_id: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=1, max_length=256)
    image: ImagePayload
    qr_polygon: list[tuple[Annotated[float, Field(ge=0,le=1,allow_inf_nan=False)], Annotated[float, Field(ge=0,le=1,allow_inf_nan=False)]]] | None = Field(default=None,min_length=4,max_length=4)

class PlaceResult(BaseModel):
    status: Literal['match', 'non_match', 'inconclusive', 'not_configured']
    decision: str
    valid_match_count: int | None = Field(default=None, ge=0)
    inlier_count: int | None = Field(default=None, ge=0)
    inlier_ratio: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    algorithm: str = 'SIFT + Ratio test + RANSAC Homography'
    reference_label: str | None = None
    reference_count: int = 1
    comparisons: list[dict] = Field(default_factory=list)
    reference_id: str | None = None
    thresholds: dict | None = None
    reference_keypoints: int | None = None
    query_keypoints: int | None = None
    match_image_url: str | None = None

class PlaceRegistration(BaseModel):
    mode: Literal["append","replace"] = "append"
    label: str = Field(default="",max_length=80)
    place_id: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')
    image: ImagePayload
    min_inliers: int = Field(default=20, ge=4, le=5000)
    min_ratio: float = Field(default=0.4, gt=0, le=1)
    ratio_test: float = Field(default=0.75, gt=0.1, lt=1)
    reprojection_px: float = Field(default=3.0, gt=0, le=20)

class CalibrationSample(BaseModel):
    attempt_id: UUID
    label: Literal['direct','relay','remove']

class CollectionReady(BaseModel):
    session_id: str
    place_id: str
    token: str
    student_id: str = Field(min_length=1,max_length=80)

class CollectionStart(BaseModel):
    client_id: str
    label: Literal['direct','relay']
    count: int = Field(default=20,ge=1,le=10000)
    purpose: Literal['calibration','evaluation'] = 'calibration'

class CalibrationApply(BaseModel):
    threshold_ms: float = Field(ge=0, allow_inf_nan=False)
