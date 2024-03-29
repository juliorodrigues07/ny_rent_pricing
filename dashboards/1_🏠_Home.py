from warnings import filterwarnings
from datetime import datetime
from typing import Dict
from os import getcwd
import numpy as np
import json
from sklearn.preprocessing import LabelEncoder
from pandas.api.types import is_integer_dtype
from pandas.api.types import is_float_dtype
from cerberus import Validator
import streamlit as st
import pandas as pd
import joblib


st.set_page_config(layout="wide", page_title="Rent Pricing", page_icon=":heavy_dollar_sign:")
filterwarnings('ignore', category=FutureWarning)


@st.cache_data
def load_model(file_name: str) -> any:

    try:
        model = joblib.load(f'{getcwd()}/../models/{file_name}_model.pkl')
        return model
    except (IsADirectoryError, NotADirectoryError, FileExistsError, FileNotFoundError):
        print("Model not found or doesn't exists!")
        exit()


@st.cache_data
def load_dataset(file_name: str) -> pd.DataFrame:

    try:
        df = pd.read_csv(f'{getcwd()}/../datasets/{file_name}.csv')
    except (IsADirectoryError, NotADirectoryError, FileExistsError, FileNotFoundError):
        print("Dataset not found or doesn't exists!")
        exit()

    df = df.rename(columns={
        'nome': 'Name',
        'host_id': 'Host ID',
        'host_name': 'Host Name',
        'bairro_group': 'Borough',
        'bairro': 'District',
        'latitude': 'Latitude',
        'longitude': 'Longitude',
        'room_type': 'Room Type',
        'price': 'Price',
        'minimo_noites': 'Minimum Nights',
        'numero_de_reviews': 'Reviews',
        'ultima_review': 'Last Review',
        'reviews_por_mes': 'Monthly Reviews',
        'calculado_host_listings_count': 'Number of Listings',
        'disponibilidade_365': "Days Available"
    })
    return df


def validate_input(input_data: Dict) -> (bool, Dict):

    schema = {
        'host_id': {'type': 'integer', 'required': True, 'empty': False},
        'host_name': {'type': 'string', 'required': True, 'empty': False},
        'borough': {'type': 'string', 'allowed': list(st.session_state['df']['Borough'].unique()),
                    'required': True, 'empty': False},
        'district': {'type': 'string', 'allowed': list(st.session_state['df']['District'].unique()),
                     'required': True, 'empty': False},
        'latitude': {'type': 'float', 'min': -90.0, 'max': 90.0, 'required': True, 'empty': False},
        'longitude': {'type': 'float', 'min': -180.0, 'max': 180.0, 'required': True, 'empty': False},
        'room_type': {'type': 'string', 'allowed': list(st.session_state['df']['Room Type'].unique()),
                      'required': True, 'empty': False},
        'min_nights': {'type': 'integer', 'min': 1, 'required': True, 'empty': False},
        'reviews': {'type': 'integer', 'min': 0, 'required': False, 'empty': False},
        'last_review': {'type': 'date', 'nullable': True, 'required': False, 'empty': True},
        'monthly_reviews': {'type': 'float', 'min': 0.0, 'required': True, 'empty': False},
        'host_listings': {'type': 'integer', 'min': 1, 'required': True, 'empty': False},
        'availability': {'type': 'integer', 'min': 0, 'max': 365, 'required': True, 'empty': False},
        'model_name': {'type': 'string', 'allowed': ['LightGBM', 'XGBoost'],
                       'required': True, 'empty': False}
    }
    input_validator = Validator(schema)

    if input_validator.validate(input_data) is False:
        print(input_validator.errors)

    return input_validator.validate(input_data), input_validator.errors


def discretize_values(df: pd.DataFrame, column: str) -> pd.DataFrame:

    filterwarnings('ignore')

    # Encodes entire columns of categorical data
    encoding = LabelEncoder()

    encoding.fit(df[column])
    df[column] = encoding.transform(df[column])

    return df


def predict_instance(input_data: Dict, algorithm: str) -> float:

    input_data.pop('model_name')
    if input_data['last_review'] is None:
        input_data['last_review'] = 'N/A'

    instance = pd.DataFrame([input_data])
    instance = instance.rename(columns={
        'host_id': 'Host ID',
        'host_name': 'Host Name',
        'borough': 'Borough',
        'district': 'District',
        'latitude': 'Latitude',
        'longitude': 'Longitude',
        'room_type': 'Room Type',
        'min_nights': 'Minimum Nights',
        'reviews': 'Reviews',
        'last_review': 'Last Review',
        'monthly_reviews': 'Monthly Reviews',
        'host_listings': 'Number of Listings',
        'availability': 'Days Available'
    })

    try:
        instance = instance.drop(['ID', 'Name', 'Price'], axis='columns')
    except KeyError:
        pass

    # Preprocessing and discretization
    if not is_integer_dtype(instance['Last Review']) and input_data['last_review'] != 'N/A':
        instance['Last Review'] = pd.to_datetime(instance['Last Review'])
        instance['Last Review'] = instance['Last Review'].apply(lambda row: f'{str(row.year)}-{str(row.month)}')

    with open(f'{getcwd()}/../models/matches.json', 'r') as encode_file:
        encodes = json.load(encode_file)

    for col in instance.columns.values:
        if not is_float_dtype(instance[col]) and not is_integer_dtype(instance[col]):

            # Gets the associated values to the column keys (-1 if the key isn't known)
            instance[col] = instance[col].apply(lambda x: encodes[col].get(x, -1))

    # Gets the binning threshold file generated in preprocessing
    with open(f'{getcwd()}/../models/bins.json', 'r') as file:
        bins = json.load(file)

    # Binning mapping
    for feature in bins:
        binned_feature = np.digitize(instance[feature], bins[feature])
        instance[feature] = binned_feature - 1

    # Prediction
    model = load_model(file_name=algorithm)
    prediction = model.predict(instance)
    price = round(prediction[0], 2)

    return price


if __name__ == '__main__':

    if 'df' not in st.session_state:
        st.session_state['df'] = load_dataset(file_name='pricing')

    try:
        st.sidebar.image(f'{getcwd()}/../assets/stock.png', width=280)
    except (IsADirectoryError, NotADirectoryError, FileExistsError, FileNotFoundError):
        print("Image not found or doesn't exists!")

    # Property form
    form1 = st.form(key='options')
    form1.title('NY Price Predictor')
    form1.header('Property Specifications')
    col1, col2, col3, col4 = form1.columns(4)

    # Inputs, buttons, select boxes, slider and warnings
    host_id = col1.number_input(label="Host ID", value=1, placeholder='Insert the number here...')

    latitude = col1.number_input(label='Latitude', value=0.000000, placeholder='Insert the number here...')
    latitude_warning = col1.container()

    longitude = col1.number_input(label='Longitude', value=0.000000, placeholder='Insert the number here...')
    longitude_warning = col1.container()

    host_name = col2.text_input(label='Host Name', placeholder='Insert the name here...').strip()
    hostname_warning = col2.container()

    min_nights = col2.number_input(label='Minimum Nights', value=1, placeholder='Insert the number here...')
    minnights_warning = col2.container()

    host_listings = col2.number_input(label='Listings per Host', value=1, placeholder='Insert the number here...')
    hostlistings_warning = col2.container()

    borough = col3.selectbox(label='Select the Borough', options=st.session_state['df']['Borough'].unique())
    district = col3.selectbox(label='Select the District', options=st.session_state['df']['District'].unique())
    room_type = col3.selectbox(label='Select the Room Type', options=st.session_state['df']['Room Type'].unique())

    reviews = col4.number_input(label='Number of Reviews', value=0, placeholder='Insert the number here...')
    reviews_warning = col4.container()

    monthly_reviews = col4.number_input(label='Monthly Reviews Rate', value=0.0, placeholder='Insert the number here...')
    monthlyreviews_warning = col4.container()

    last_review = col4.date_input(label='Last Review Date', value=None, max_value=datetime.now(), format="DD/MM/YYYY")

    availability = form1.slider(label='Days Available per Year', min_value=0, max_value=365, value=70)
    algorithm = form1.selectbox(label='Select the ML Algorithm', options=['LightGBM', 'XGBoost'])
    submit_button = form1.form_submit_button('Predict')

    prediction = st.container()

    input_data = {
        'host_id': host_id,
        'host_name': host_name,
        'borough': borough,
        'district': district,
        'latitude': latitude,
        'longitude': longitude,
        'room_type': room_type,
        'min_nights': min_nights,
        'reviews': reviews,
        'last_review': last_review,
        'monthly_reviews': monthly_reviews,
        'host_listings': host_listings,
        'availability': availability,
        'model_name': algorithm
    }

    model_name = str()
    match algorithm:
        case 'LightGBM':
            model_name = 'lgbm'
        case 'XGBoost':
            model_name = 'xgb'
        case _:
            print("ML model not available or doesn't exists")
            exit()

    check, errors = validate_input(input_data=input_data)
    if submit_button is True and check is True:
        price = predict_instance(input_data=input_data, algorithm=model_name)
        prediction.success(f'Price: US$ {price}')

    elif submit_button is True and check is False:
        for key in errors.keys():
            match key:
                case 'latitude':
                    latitude_warning.error('Latitude values must be between -90 and 90!')
                case 'longitude':
                    longitude_warning.error('Longitude values must be between -180 and 180!')
                case 'min_nights':
                    minnights_warning.error('Minimum nights must be greater than 0!')
                case 'reviews':
                    reviews_warning.error('Number of reviews must not be negative!')
                case 'monthly_reviews':
                    monthlyreviews_warning.error('Monthly reviews rate must not be negative!')
                case 'host_name':
                    hostname_warning.error('Host name cannot be empty!')
                case 'host_listings':
                    hostlistings_warning.error('Number of listings per host must be greater than 0!')
                case _:
                    print("Data doesn't exist!")
