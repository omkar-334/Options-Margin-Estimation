import gzip
import json
import os
import shutil
from datetime import datetime
from typing import Literal, Union

import jmespath
import pandas as pd
import requests
from dotenv import load_dotenv
from memoization import cached

### Part 1


def get_option_chain_data(
    instrument_name: str, expiry_date: str, side: Literal["PE", "CE", None]
) -> pd.DataFrame:
    """Retrieves the option chain data from the NSE Official API.

    Args:
        instrument_name (str): Name of the instrument (e.g., NIFTY or BANKNIFTY).
        expiry_date (str): The expiration date of the options, in YYYY-MM-DD format.
        side (str): Type of option to retrieve. Use "PE" for Put and "CE" for Call.

    Returns:
        pd.DataFrame: Returns a DataFrame with columns: instrument_name, strike_price, side, and bid/ask.
    """
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={instrument_name}"
    results = nsefetch(url)
    if not results or "records" not in results:
        return None
    df = pd.DataFrame(results["records"]["data"])
    df["expiryDate"] = pd.to_datetime(df["expiryDate"], format="%d-%b-%Y")

    expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d")

    df = df[df["expiryDate"] == expiry_date]

    if not side:
        pedf = normalize(df, "PE")
        cedf = normalize(df, "CE")
        df = pd.concat([pedf, cedf], ignore_index=True)
    else:
        df = normalize(df, side)

    df["instrument_name"] = instrument_name
    return df


def normalize(df, side):
    """normalizes JSON rows into new columns.
    Source - AI (code generation)"""
    if side == "PE":
        column = "bidprice"
    elif side == "CE":
        column = "askPrice"

    subdf = pd.json_normalize(df[side])[["strikePrice", column]]
    subdf.rename(columns={column: "bid/ask"}, inplace=True)
    subdf["side"] = side

    df = pd.merge(
        df.drop(columns=["CE", "PE"]),
        subdf,
        on="strikePrice",
        suffixes=("", "_expanded"),
    )

    return df


### Part 2


def calculate_margin_and_premium(data: pd.DataFrame) -> pd.DataFrame:
    """Calculates the margin required and premium earned, using the Upstox API.

    Args:
        data (pd.DataFrame): _description_

    Returns:
        pd.DataFrame: Returns the modified DataFrame with new columns: margin_required and premium_earned.
    """
    data["margin_required"] = data.apply(calculate_margin, axis=1)
    data["premium_earned"] = data.apply(calculate_premium, axis=1)
    return data


def calculate_margin(row: pd.Series) -> int:
    """Calculates the `margin_required`.

    Args:
        row (pd.Series): Dataframe row

    Returns:
        int: Margin required
    """
    instrument_name = row["instrument_name"]
    side = row["side"]
    key = get_instrument_key(
        instrument_name, row["expiryDate"], row["strikePrice"], side
    )
    print(key)
    lot_size = get_lot_size(instrument_name)

    transaction = "BUY" if side == "PE" else "SELL"
    margin = get_margin(key, lot_size, transaction)
    return margin


def calculate_premium(row: pd.Series) -> int:
    """Calculates the `premium_earned`.
    Source - assessment

    Args:
        row (pd.Series): Dataframe row

    Returns:
        int: Premium earned
    """
    instrument_name = row["instrument_name"]
    lot_size = get_lot_size(instrument_name)
    premium = row["bid/ask"] * lot_size
    return premium


def get_margin(instrument_key: str, lot_size: int, transaction_type: str) -> int:
    """Gets the margin required from the Upstox API.
    Source - https://upstox.com/developer/api-documentation/margin

    Args:
        instrument_key (str): Upstox instrument key
        lot_size (int): Lot size of the instrument
        transaction_type (str): Type of the transaction

    Returns:
        int: Margin required
    """
    url = "https://api.upstox.com/v2/charges/margin"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {os.getenv('TOKEN')}",
    }
    data = {
        "instruments": [
            {
                "instrument_key": instrument_key,
                "quantity": lot_size,
                "transaction_type": transaction_type,
                "product": "D",
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    response = response.json()
    if not response or "data" not in response:
        return None
    margin = response["data"].get("required_margin", 0)
    return margin


### Auxiliary Functions


def get_lot_size(instrument_name: str = None) -> Union[str, dict, None]:
    """Gets the Lot size of the instrument."""
    filename = download_lots_json()
    if not filename:
        return
    with open(filename, "r") as file:
        result = json.load(file)
        if instrument_name:
            return result.get(instrument_name, None)
        return result


def get_instrument_key(
    instrument_name: str,
    expiry_date: pd.Timestamp,
    strike_price: int,
    instrument_type: Literal["PE", "CE"],
) -> str:
    """Gets the Upstox instrument_key based on Margin parameters.
    Source - https://community.upstox.com/t/seeking-help-with-instrument-keys-for-specific-options-in-upstox-api/3195/4

    Args:
        instrument_name (str): Name of the instrument
        expiry_date (pd.Timestamp): Date of expiry
        strike_price (int): Strike price
        instrument_type (Literal['PE', 'CE']): Type of the instrument (side)

    Returns:
        str: _description_
    """
    filename = download_instrument_json()
    if not filename:
        return
    df = pd.read_json(filename)

    date_str = expiry_date.strftime("%d %b %y").upper()

    trading_symbol = f"{instrument_name} {strike_price} {instrument_type} {date_str}"
    filtered_df = df[df["trading_symbol"] == trading_symbol]
    if not filtered_df.empty:
        return filtered_df.iloc[0]["instrument_key"]

    return None


### Authentication Functions


def authenticate():
    """Authenticates the Upstox API and retrieves access token.
    Source - https://upstox.com/developer/api-documentation/authentication/"""
    load_dotenv()
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    REDIRECT_URL = os.getenv("REDIRECT_URL")

    url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URL}"

    print(f"Go to this url and manually authenticate. \n {url}")
    code = input("Enter the code - ")

    url = "https://api.upstox.com/v2/login/authorization/token"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URL,
        "grant_type": "authorization_code",
    }

    response = requests.post(url, headers=headers, data=data)
    print(response.json())
    token = response.json().get("access_token", "")
    print(code)
    print(token)
    write_to_env(code, token)
    load_dotenv()


def write_to_env(code, token):
    """Writes the code and access tokens to .env file.
    Source - AI (code generation)"""
    env_variables = {"CODE": code, "TOKEN": token}

    with open(".env", "a") as env_file:
        for key, value in env_variables.items():
            if f"{key}=" not in open(".env").read():
                env_file.write(f"{key}={value}\n")


### Fetch / Download Functions


def nsefetch(payload: dict) -> dict:
    """A function to call the NSE API using custom headers.

    Args:
        payload (dict): payload dictionary.

    Returns:
        dict: response dictionary.
    """
    try:
        output = requests.get(payload, headers=headers).json()
    except ValueError:
        s = requests.Session()
        output = s.get("http://nseindia.com", headers=headers)
        output = s.get(payload, headers=headers).json()
    return output


headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9,en-IN;q=0.8,en-GB;q=0.7",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Microsoft Edge";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
}


@cached(ttl=30 * 24 * 3600)
def download_lots_json() -> str:
    """Downloads a json file consisting of indices/equities and their lot sizes.
    Source - https://github.com/aeron7/nsepython/issues/42

    Returns:
        str: The name of the downloaded json file
    """
    LOTS_FILE = "lots_data.json"

    if os.path.exists(LOTS_FILE):
        return LOTS_FILE

    res = requests.post(
        "https://open-web-scanx.dhan.co/scanx/allfut",
        json=json.loads(
            '{"Data":{"Seg":2,"Instrument":"FUT","Count":200,"Page_no":1,"ExpCode":-1}}'
        ),
        headers={"content-type": "application/json; charset=UTF-8"},
        cookies={},
        auth=(),
    )

    lots = jmespath.search("data.list[*].[sym, fo_dt[0].lot_type]", res.json())
    result = {x[0]: int(x[1].split()[0]) for x in lots}

    with open(LOTS_FILE, "w") as file:
        json.dump(result, file)

    return LOTS_FILE


def download_instrument_json() -> str:
    """Downloads a json file from Upstox consisting of instrument_keys.
    Source - AI (code generation, unzipping).

    Returns:
        str: The name of the downloaded json file
    """
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    compressed_file = "NSE.json.gz"
    output_file = "NSE.json"

    if os.path.exists(output_file):
        return output_file

    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(compressed_file, "wb") as file:
            file.write(response.content)
    else:
        return False

    with gzip.open(compressed_file, "rb") as f_in:
        with open(output_file, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    os.remove(compressed_file)
    return output_file
