import datetime as dt

import pandas as pd
import pytest
import intake
from intake_google_analytics.source import GoogleAnalyticsAPI
from pandas.api.types import (is_datetime64_any_dtype, is_float_dtype,
                              is_integer_dtype)
from pandas.testing import assert_frame_equal


def test_parse_fields_wrong_style():
    with pytest.raises(ValueError):
        GoogleAnalyticsAPI._parse_fields(['ga:users'], style='nope')


def test_parse_metrics():
    metrics = ['ga:users']
    parsed = GoogleAnalyticsAPI._parse_fields(metrics, style='metrics')
    assert parsed == [{'expression': 'ga:users'}]

    metrics = ['ga:users', 'ga:session']
    parsed = GoogleAnalyticsAPI._parse_fields(metrics, style='metrics')
    assert parsed == [{'expression': 'ga:users'}, {'expression': 'ga:session'}]

    metrics = ['ga:users', {"expression": 'ga:session', 'alias': 'Session'}]
    parsed = GoogleAnalyticsAPI._parse_fields(metrics, style='metrics')
    assert parsed == [
        {'expression': 'ga:users'},
        {"expression": 'ga:session', 'alias': 'Session'}
    ]

    metrics = [{"expression": 'ga:session'}]
    parsed = GoogleAnalyticsAPI._parse_fields(metrics, style='metrics')
    assert parsed == metrics

    metrics = [{"expression": 'ga:session', 'alias': 'Session'}]
    parsed = GoogleAnalyticsAPI._parse_fields(metrics, style='metrics')
    assert parsed == metrics

    with pytest.raises(ValueError):
        metrics = [{"espresso": 'ga:session', 'alias': 'Session'}]
        GoogleAnalyticsAPI._parse_fields(metrics, style='metrics')

    with pytest.raises(ValueError):
        GoogleAnalyticsAPI._parse_fields([1], style='metrics')


def test_parse_dimensions():
    dimensions = ['ga:userType']
    parsed = GoogleAnalyticsAPI._parse_fields(dimensions, style='dimensions')
    assert parsed == [{'name': 'ga:userType'}]

    dimensions = ['ga:userType', 'ga:date']
    parsed = GoogleAnalyticsAPI._parse_fields(dimensions, style='dimensions')
    assert parsed == [{'name': 'ga:userType'}, {'name': 'ga:date'}]

    dimensions = ['ga:userType', {'name': 'ga:date'}]
    parsed = GoogleAnalyticsAPI._parse_fields(dimensions, style='dimensions')
    assert parsed == [{'name': 'ga:userType'}, {'name': 'ga:date'}]

    dimensions = [{'name': 'ga:date'}]
    parsed = GoogleAnalyticsAPI._parse_fields(dimensions, style='dimensions')
    assert parsed == dimensions

    with pytest.raises(ValueError):
        dimensions = [{"nom": 'ga:date'}]
        GoogleAnalyticsAPI._parse_fields(dimensions, style='dimensions')

    with pytest.raises(ValueError):
        GoogleAnalyticsAPI._parse_fields([1], style='dimensions')


def test_parse_date_objects():
    assert GoogleAnalyticsAPI._parse_date('2020-03-19') == '2020-03-19'
    assert GoogleAnalyticsAPI._parse_date(dt.date(2020, 3, 19)) == '2020-03-19'
    assert GoogleAnalyticsAPI._parse_date(dt.datetime(2020, 3, 19, 16, 20, 0)) == '2020-03-19'
    assert GoogleAnalyticsAPI._parse_date(pd.to_datetime('2020-03-19 16:20:00')) == '2020-03-19'
    assert GoogleAnalyticsAPI._parse_date(pd.Timestamp(2020, 3, 19, 16, 20, 0)) == '2020-03-19'

    with pytest.raises(TypeError):
        GoogleAnalyticsAPI._parse_date(dt.timedelta(days=2))


def test_parse_date_strings():
    assert GoogleAnalyticsAPI._parse_date('yesterday') == 'yesterday'
    assert GoogleAnalyticsAPI._parse_date('today') == 'today'
    assert GoogleAnalyticsAPI._parse_date('1000DaysAgo') == '1000DaysAgo'

    with pytest.raises(ValueError):
        GoogleAnalyticsAPI._parse_date('tomorrow')

    with pytest.raises(ValueError):
        GoogleAnalyticsAPI._parse_date('πDaysAgo')


def test_query_body(monkeypatch):
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: None)

    inputs = {
        'view_id': 'VIEWID',
        'start_date': '5DaysAgo', 'end_date': 'yesterday',
        'metrics': ['ga:users']
    }
    expected_body = {'reportRequests': [
        {'dateRanges': [{'endDate': 'yesterday', 'startDate': '5DaysAgo'}],
         'hideTotals': True,
         'hideValueRanges': True,
         'includeEmptyRows': True,
         'metrics': [{'expression': 'ga:users'}],
         'viewId': 'VIEWID'}
    ]}

    client = GoogleAnalyticsAPI(None)
    body = client._build_body(**inputs)
    assert body == expected_body


def test_query_body_with_dimensions(monkeypatch):
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: None)

    inputs = {
        'view_id': 'VIEWID',
        'start_date': '5DaysAgo', 'end_date': 'yesterday',
        'metrics': ['ga:users'],
        'dimensions': ['ga:userType']
    }
    expected_body = {'reportRequests': [
        {'dateRanges': [{'endDate': 'yesterday', 'startDate': '5DaysAgo'}],
         'hideTotals': True,
         'hideValueRanges': True,
         'includeEmptyRows': True,
         'metrics': [{'expression': 'ga:users'}],
         'dimensions': [{'name': 'ga:userType'}],
         'viewId': 'VIEWID'}
    ]}

    client = GoogleAnalyticsAPI(None)
    body = client._build_body(**inputs)
    assert body == expected_body


def test_dataframe_empty_report():
    report = {
        'columnHeader':
            {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users', 'type': 'INTEGER'}]}},
            'data': {}
    }
    df = GoogleAnalyticsAPI._to_dataframe(report)
    assert df.empty


datetime_dimensions = [
    ('ga:yearMonth', '202003'),
    ('ga:date', '20200319'),
    ('ga:dateHour', '2020031916'),
    ('ga:dateHourMinute', '202003191620'),
]


@pytest.mark.parametrize('dimension', datetime_dimensions, ids=[p[0] for p in datetime_dimensions])
def test_dataframe_datetime_dimensions(dimension):
    dim, value = dimension

    report = {
        'columnHeader':
            {'dimensions': [dim],
             'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users', 'type': 'INTEGER'}]}},
            'data': {
                'rowCount': 1,
                'rows': [{'dimensions': [value],
                          'metrics': [{'values': ['1']}]}]
            }
    }
    df = GoogleAnalyticsAPI._to_dataframe(report)
    assert is_datetime64_any_dtype(df[dim])


def test_dataframe_multiple_datetime_dimensions():
    multi_column = {
        'columnHeader':
            {'dimensions': ['ga:date', 'ga:dateHourMinute'],
             'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users', 'type': 'INTEGER'}]}},
            'data': {
                'rowCount': 1,
                'rows': [{'dimensions': ['20200319', '202003191620'],
                          'metrics': [{'values': ['1']}]}]
            }
    }
    df = GoogleAnalyticsAPI._to_dataframe(multi_column)
    assert is_datetime64_any_dtype(df['ga:dateHourMinute'])
    assert is_datetime64_any_dtype(df['ga:date'])


metric_dtypes = [
    ('INTEGER', "ga:users", '1', is_integer_dtype),
    ('TIME', 'ga:sessionDuration', '1.1', is_float_dtype),
    ('PERCENT', 'ga:percentNewSessions', '1.1', is_float_dtype),
    ('CURRENCY', 'ga:goalValueAll', '1.1', is_float_dtype),
    ('FLOAT', 'ga:pageviewsPerSession', '1.1', is_float_dtype)
]


@pytest.mark.parametrize('metric', metric_dtypes, ids=[p[0] for p in metric_dtypes])
def test_dataframe_metric_dtype(metric):
    ga_type, column, value, test_func = metric

    report = {
        'columnHeader':
            {'metricHeader': {'metricHeaderEntries':
                [{'name': column, 'type': ga_type}]}},
            'data': {
                'rowCount': 1,
                'rows': [{'metrics': [{'values': [value]}]}]
            }
    }
    df = GoogleAnalyticsAPI._to_dataframe(report)
    assert test_func(df[column])


class MockGAClient():
    def __init__(self, credentials_path):
        pass

    def batchGet(self, body):
        return MockGABatch(body)


class MockGABatch():
    def __init__(self, body):
        self.body = body

    def execute(self):
        pass


def test_query_to_dataframe(monkeypatch):
    monkeypatch.setattr(MockGABatch, 'execute', lambda body: {
            'reports': [
                {'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                            'type': 'INTEGER'}]}},
                 'data': {'rowCount': 1, 'rows': [{'metrics': [{'values': ['1']}]}]}}
                ]
            }
    )
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: MockGAClient(x))

    ga_api = GoogleAnalyticsAPI(None)
    df = ga_api.query(
        'VIEWID',
        start_date='5DaysAgo', end_date='yesterday',
        metrics=['ga:user']
    )
    assert_frame_equal(df, pd.DataFrame([{'ga:users': 1}]), check_dtype=False)


def test_query_wrong_row_count(monkeypatch):
    monkeypatch.setattr(MockGABatch, 'execute', lambda body: {
            'reports': [
                {'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                            'type': 'INTEGER'}]}},
                 'data': {'rowCount': 1, 'rows': [
                     {'metrics': [{'values': ['1']}]},
                     {'metrics': [{'values': ['2']}]}
                     ]}}
                ]
            }
    )
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: MockGAClient(x))

    ga_api = GoogleAnalyticsAPI(None)
    with pytest.raises(RuntimeError):
        _ = ga_api._query(
            'VIEWID',
            start_date='5DaysAgo', end_date='yesterday',
            metrics=['ga:user']
        )


def test_query_empty_result(monkeypatch):
    monkeypatch.setattr(MockGABatch, 'execute', lambda body: {
            'reports': [
                {'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                            'type': 'INTEGER'}]}},
                 'data': {}}
                ]
            }
    )
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: MockGAClient(x))

    ga_api = GoogleAnalyticsAPI(None)
    df = ga_api.query(
        'VIEWID',
        start_date='5DaysAgo', end_date='yesterday',
        metrics=['ga:user']
    )
    assert df.empty


def test_paginated_result(monkeypatch):
    def execute(self):
        paginated = [
            {'reports': [
                {'nextPageToken': 1,
                'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                                            'type': 'INTEGER'}]}},
                 'data': {'rowCount': 6, 'rows': [
                     {'metrics': [{'values': ['1']}]}, {'metrics': [{'values': ['2']}]}
                     ]}}
                ]
             },
            {'reports': [
                {'nextPageToken': 2,
                'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                                            'type': 'INTEGER'}]}},
                 'data': {'rowCount': 6, 'rows': [
                     {'metrics': [{'values': ['3']}]}, {'metrics': [{'values': ['4']}]}
                     ]}}
                ]
             },
            {'reports': [
                {'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                                            'type': 'INTEGER'}]}},
                 'data': {'rowCount': 6, 'rows': [
                     {'metrics': [{'values': ['5']}]}, {'metrics': [{'values': ['6']}]}
                     ]}}
                ]
             },
        ]

        page_token = self.body['reportRequests'][0].get('pageToken', 0)
        return paginated[page_token]

    monkeypatch.setattr(MockGABatch, 'execute', execute)
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: MockGAClient(x))

    ga_api = GoogleAnalyticsAPI(None)
    df = ga_api.query(
        'VIEWID',
        start_date='5DaysAgo', end_date='yesterday',
        metrics=['ga:user']
    )
    assert len(df) == 6


def test_load_dataset(monkeypatch):
    monkeypatch.setattr(MockGABatch, 'execute', lambda body: {
            'reports': [
                {'columnHeader': {'metricHeader': {'metricHeaderEntries': [{'name': 'ga:users',
                                                            'type': 'INTEGER'}]}},
                 'data': {'rowCount': 1, 'rows': [{'metrics': [{'values': ['1']}]}]}}
                ]
            }
    )
    monkeypatch.setattr(GoogleAnalyticsAPI, 'create_client', lambda x: MockGAClient(x))

    ds = intake.open_google_analytics_query(
        'VIEWID',
        start_date='5DaysAgo', end_date='yesterday',
        metrics=['ga:user'],
        credentials_path=None
    )

    assert ds.name == 'google_analytics_query'
    assert ds.container == 'dataframe'

    yaml = """sources:
  google_analytics_query:
    args:
      credentials_path: null
      end_date: yesterday
      metrics:
      - ga:user
      start_date: 5DaysAgo
      view_id: VIEWID
    description: ''
    driver: intake_google_analytics.source.GoogleAnalyticsQuerySource
    metadata: {}
"""

    assert ds.yaml() == yaml

    df = ds.read()
    assert_frame_equal(df, pd.DataFrame([{'ga:users': 1}]), check_dtype=False)
