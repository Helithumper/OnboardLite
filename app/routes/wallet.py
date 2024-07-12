import json
import os
import uuid
from typing import Optional

import requests
from airpress import PKPass
from fastapi import APIRouter, Cookie, Depends, Request, Response
from ..models.info import InfoModel
from ..models.user import PublicContact, UserModel, user_to_dict
from sqlalchemy.orm import selectinload
from sqlmodel import select
from ..util.authentication import Authentication
from ..util.database import get_session
from ..util.errors import Errors

router = APIRouter(
    prefix="/wallet", tags=["API", "MobileWallet"], responses=Errors.basic_http()
)


def get_img(url):
    """
    Used to get Discord image.
    """
    resp = requests.get(url, stream=True)
    status = resp.status_code
    if status < 400:
        return resp.raw.read()
    else:
        return get_img("https://cdn.hackucf.org/PFP.png")


def apple_wallet(user_data):
    """
    User data -> Apple Wallet blob
    """
    # Create empty pass package
    p = PKPass()

    is_ops = True if user_data.get("ops_email", False) else False

    # Add locally stored assets
    with open(
        os.path.join(
            os.path.dirname(__file__), "..", "static", "apple_wallet", "icon.png"
        ),
        "rb",
    ) as file:
        ico_data = file.read()
        p.add_to_pass_package(("icon.png", ico_data))

    with open(
        os.path.join(
            os.path.dirname(__file__), "..", "static", "apple_wallet", "icon@2x.png"
        ),
        "rb",
    ) as file:
        ico_data = file.read()
        p.add_to_pass_package(("icon@2x.png", ico_data))

    pass_json = {
        "passTypeIdentifier": "pass.org.hackucf.join",
        "formatVersion": 1,
        "teamIdentifier": "VWTW9R97Q4",
        "organizationName": "Hack@UCF",
        "serialNumber": str(uuid.uuid4()),
        "description": "Hack@UCF Membership ID",
        "locations": [
            {
                "latitude": 28.601366109876327,
                "longitude": -81.19867691612126,
                "relevantText": "You're near the CyberLab!",
            }
        ],
        "foregroundColor": "#D2990B",
        "backgroundColor": "#1C1C1C",
        "labelColor": "#ffffff",
        "logoText": "",
        "barcodes": [
            {
                "format": "PKBarcodeFormatQR",
                "message": user_data.get("id", "Unknown_ID"),
                "messageEncoding": "iso-8859-1",
                "altText": user_data.get("discord", {}).get("username", None),
            }
        ],
        "generic": {
            "primaryFields": [
                {
                    "label": "Name",
                    "key": "name",
                    "value": user_data.get("first_name", "")
                    + " "
                    + user_data.get("surname", ""),
                }
            ],
            "secondaryFields": [
                {
                    "label": "Infra Email",
                    "key": "infra",
                    "value": user_data.get("infra_email", "Not Provisioned"),
                }
            ],
            "backFields": [
                {
                    "label": "View Profile",
                    "key": "view-profile",
                    "value": "You can view and edit your profile at https://join.hackucf.org/profile.",
                    "attributedValue": "You can view and edit your profile at <a href='https://join.hackucf.org/profile'>join.hackucf.org</a>.",
                },
                {
                    "label": "Check In",
                    "key": "check-in",
                    "value": "At a meeting? Visit https://hackucf.org/signin to sign in",
                    "attributedValue": "At a meeting? Visit <a href='https://hackucf.org/signin'>hackucf.org/signin</a> to sign in.",
                },
            ],
        },
    }

    # I am duplicating the file reads because it's easier than re-setting file pointers to the start of each file.
    # I think.

    # User profile image
    discord_img = user_data.get("discord", {}).get("avatar", False)
    if discord_img:
        img_data = get_img(discord_img)
        p.add_to_pass_package(("thumbnail.png", img_data))

        img_data = get_img(discord_img)
        p.add_to_pass_package(("thumbnail@2x.png", img_data))

    # Role-based logo.
    if is_ops:
        with open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "static",
                "apple_wallet",
                "logo_ops@2x.png",
            ),
            "rb",
        ) as file:
            ico_data = file.read()
            p.add_to_pass_package(("logo@2x.png", ico_data))

        with open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "static",
                "apple_wallet",
                "logo_ops.png",
            ),
            "rb",
        ) as file:
            ico_data = file.read()
            p.add_to_pass_package(("logo.png", ico_data))
    else:
        with open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "static",
                "apple_wallet",
                "logo_reg@2x.png",
            ),
            "rb",
        ) as file:
            ico_data = file.read()
            p.add_to_pass_package(("logo@2x.png", ico_data))

        with open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "static",
                "apple_wallet",
                "logo_reg.png",
            ),
            "rb",
        ) as file:
            ico_data = file.read()
            p.add_to_pass_package(("logo.png", ico_data))

    pass_data = json.dumps(pass_json).encode("utf8")

    p.add_to_pass_package(("pass.json", pass_data))

    # Add locally stored credentials
    with open(
        os.path.join(os.path.dirname(__file__), "..", "config/pki/hackucf.key"), "rb"
    ) as key, open(
        os.path.join(os.path.dirname(__file__), "..", "config/pki/hackucf.pem"), "rb"
    ) as cert:
        # Add credentials to pass package
        p.key = key.read()
        p.cert = cert.read()

    # As we've added credentials to pass package earlier we don't need to supply them to `.sign()`
    # This is an alternative to calling .sign() method with credentials as arguments.
    p.sign()

    return p


@router.get("/")
async def get_root():
    """
    Get API information.
    """
    return InfoModel(
        name="Onboard for Mobile Wallets",
        description="Apple Wallet support.",
        credits=[
            PublicContact(
                first_name="Jonathan",
                surname="Styles",
                ops_email="jstyles@hackucf.org",
            )
        ],
    )


@router.get("/apple")
@Authentication.member
async def aapl_gen(
    request: Request,
    token: Optional[str] = Cookie(None),
    user_jwt: Optional[object] = {},
    session=Depends(get_session),
):
    statement = (
        select(UserModel)
        .where(UserModel.id == user_jwt["id"])
        .options(selectinload(UserModel.discord), selectinload(UserModel.ethics_form))
    )
    user_data = user_to_dict(session.exec(statement).one_or_none())

    p = apple_wallet(user_data)

    return Response(
        content=bytes(p),
        media_type="application/vnd.apple.pkpass",
        headers={"Content-Disposition": 'attachment; filename="hackucf.pkpass"'},
    )
