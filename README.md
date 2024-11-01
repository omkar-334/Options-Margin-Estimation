# Assessment

## Part 1: Retrieve Option Chain Data

```
def get_option_chain_data(
    instrument_name: str, expiry_date: str, side: Literal["PE", "CE", None]
) -> pd.DataFrame:
    """
    Retrieves the option chain data from the NSE Official API.

    Args:
        instrument_name (str): Name of the instrument (e.g., NIFTY or BANKNIFTY).
        expiry_date (str): The expiration date of the options, in YYYY-MM-DD format.
        side (str): Type of option to retrieve. Use "PE" for Put and "CE" for Call.

    Returns:
        pd.DataFrame: Returns a DataFrame with columns: instrument_name, strike_price, side, and bid/ask.
    """
```
The Upstox API for retrieving option chain data was a bit confusing to understand, and did not return results sometimes. Since I had used the NSE official API and scraped the website regularly for announcements, Board meetings, corporate action, I had chosen this method.   
The Option Chain Data is fetched from the NSE API (`f"https://www.nseindia.com/api/option-chain-indices?symbol={instrument_name}"`).

Your requirement for this function was a bit ambigous to understand, so  I had made a few assumptions. - 
1. Retrieve Option Chain data
2. Filter by `expiry_date`
3. Filter by `side`. If not mentioned, return both.
4. Each row is a json and it is normalized and merged with the dataframe.
4. For each `strike_price`, choose `bid_price` or `ask_price` based on the `side`.


## Part 2: Calculate Margin and Premium Earned
```
def calculate_margin_and_premium(data: pd.DataFrame) -> pd.DataFrame:
    """Calculates the margin required and premium earned, using the Upstox API.

    Args:
        data (pd.DataFrame): _description_

    Returns:
        pd.DataFrame: Returns the modified DataFrame with new columns: margin_required and premium_earned.
    """
```

The Upstox API is used for calculating the required margin.   
This function takes about 2-5 minutes, since it sends an API request for each row.  

1. `margin_required` - Uses the Upstox API.  
Assumptions - 
    - ```transaction = "BUY" if side == "PE" else "SELL"```  
    - ```"product" = "D"```
    
The `required_margin` value is extracted from the API response.  
The instrument Key for each set of parameters is obtained from https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz.  

2. `premium_earned` = `bid/ask` price * `lot_size`  
The Lot size for an index/equity is obtained from https://open-web-scanx.dhan.co/scanx/allfut.    

The functions for obtaining the lot_size and instrument_key download the respective file and fetch from the file.

## Setup
In order to use the second function (`calculate_margin_and_premium`), you need to authenticate the Upstox API.
Create a `.env` file and enter these secrets.
```
CLIENT_ID=
CLIENT_SECRET=
REDIRECT_URL=
CODE=
TOKEN=
```
However, if you only have the `client_id`, `client_secret` and `redirect_url`, you can use the `authenticate()` function and generate an access token.  
The access token expires at 3.30 PM everyday, irrespective of the time of generation.


## Example

```
instrument_name = 'BANKNIFTY'
expiry_date = '2024-12-24'
side = 'PE'

df = get_option_chain_data(instrument_name, expiry_date, side)

df = calculate_margin_and_premium(df)

df.to_csv('example.csv')
```

Open `example.csv` to view the data for this example.  
For each function, the source is listed in the description.  