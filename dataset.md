# Dataset Overview

This dataset contains one month of Indian derivatives market data under `Data/allData/`. It is organized by trading date, and each date folder contains two subfolders:

- `Futures (Continuous)/` - continuous futures data for major index underlyings
- `Options/` - option contract data for individual option instruments

The dataset covers trading sessions in November 2022. The date folders currently present are:

- `NSE_20221101`
- `NSE_20221102`
- `NSE_20221103`
- `NSE_20221104`
- `NSE_20221107`
- `NSE_20221109`
- `NSE_20221110`
- `NSE_20221111`
- `NSE_20221114`
- `NSE_20221115`
- `NSE_20221116`
- `NSE_20221117`
- `NSE_20221118`
- `NSE_20221121`
- `NSE_20221122`
- `NSE_20221123`
- `NSE_20221124`
- `NSE_20221125`
- `NSE_20221128`
- `NSE_20221129`
- `NSE_20221130`

That is 20 trading days in total.

## Directory Structure

A typical path looks like this:

```text
Data/allData/NSE_20221101/
  Futures (Continuous)/
    BANKNIFTY-I.csv
    BANKNIFTY-II.csv
    BANKNIFTY-III.csv
    FINNIFTY-I.csv
    FINNIFTY-II.csv
    FINNIFTY-III.csv
    NIFTY-I.csv
    NIFTY-II.csv
    NIFTY-III.csv
  Options/
    BANKNIFTY22110330500PE.csv
    BANKNIFTY22110336000CE.csv
    FINNIFTY22110719500CE.csv
    NIFTY22110314550PE.csv
    ...
```

## Futures Data

The futures folder contains continuous futures files for three underlyings:

- `NIFTY`
- `BANKNIFTY`
- `FINNIFTY`

For each underlier, there are three files:

- `UNDERLIER-I.csv`
- `UNDERLIER-II.csv`
- `UNDERLIER-III.csv`

Example:

- `NIFTY-I.csv`
- `NIFTY-II.csv`
- `NIFTY-III.csv`

For the intended use case, only the `-I.csv` contract is relevant.

These files appear to contain event-level trade/quote updates throughout the trading session.

## Options Data

The `Options/` folder contains one CSV per option contract for that trading day. Each file name encodes the instrument identity.

### Option filename pattern

The general pattern is:

```text
UNDERLIER + EXPIRY(YYMMDD) + STRIKE + OPTION_TYPE.csv
```

Examples:

- `NIFTY22110314550PE.csv`
- `BANKNIFTY22112443200CE.csv`
- `FINNIFTY22110719500CE.csv`

### How to parse the name

For `NIFTY22110314550PE.csv`:

- Underlier: `NIFTY`
- Expiry date: `221103`
- Strike price: `14550`
- Option type: `PE`

For `BANKNIFTY22112443200CE.csv`:

- Underlier: `BANKNIFTY`
- Expiry date: `221124`
- Strike price: `43200`
- Option type: `CE`

For `FINNIFTY22110719500CE.csv`:

- Underlier: `FINNIFTY`
- Expiry date: `221107`
- Strike price: `19500`
- Option type: `CE`

### Option type codes

- `CE` = Call Option
- `PE` = Put Option

## File Format

All CSV files in this dataset use the same 5-column structure and do not appear to include a header row.

Columns:

1. `Date`
2. `Time`
3. `Price`
4. `Volume`
5. `Open Interest`

### Example row

```text
20221101,09:15:02,0.25,1,114700
```

Interpreting the row:

- Date: `20221101`
- Time: `09:15:02`
- Price: `0.25`
- Volume: `1`
- Open Interest: `114700`

## Observed Data Characteristics

- Data is time-stamped intraday market data.
- Rows are ordered chronologically within each file.
- The dataset is suitable for intraday options/futures analysis, backtesting, and feature engineering.
- Futures and options can be joined using the trading date and time, with options also requiring instrument parsing from the filename.

## Trading Context

The intended workflow is to trade options using both:

- the option contract files in `Options/`
- the continuous futures files in `Futures (Continuous)/`

The futures data is used as supporting market context, while execution or signal evaluation is likely focused on options.

## Practical Notes

- The folder name `NSE_YYYYMMDD` corresponds directly to the trading date.
- The option expiration date is embedded in the filename, not in a separate metadata file.
- Some option files may correspond to contracts that are not present for every strike on every date.
- The dataset is large and highly granular, so parsing and storage strategy matter for downstream analysis.

## Suggested Use For Downstream Analysis

If you are using this dataset for research or model-building, a good workflow is:

1. Parse the trading-date folder name.
2. Parse the option instrument name into underlier, expiry, strike, and type.
3. Load the tick data for both futures and options.
4. Align on date and time for any intraday strategy logic.
5. Use futures as the reference market context and options as the tradable instruments.

## Short Summary

This is a one-month intraday derivatives dataset for NSE index products. It contains per-day folders with continuous futures series for `NIFTY`, `BANKNIFTY`, and `FINNIFTY`, plus a large universe of individual option contract CSVs. Each CSV contains 5 fields: date, time, price, volume, and open interest, with filenames encoding the instrument identity and, for options, expiry/strike/type information.
