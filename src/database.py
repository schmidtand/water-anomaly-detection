import logging
import pandas as pd
import datetime
import numpy as np
import os

import psycopg2

import src.plot


ONLINE = True


class ReadException(Exception):
    def __init__(self, e):
        self.e = e


class Database:

    instance = None

    def get_instance():
        return Database.instance


    def __init__(self, path="test/res"):
        Database.instance = self
        self.path = path
    

    def connect(self, **connection_config):
        logging.info("connect to %s", {k: "".join(["*" for _ in v]) if k == "password" else v for k,v in connection_config.items()})

        self.connection_config = connection_config

        self._connect()
    

    def _connect(self):
        try:
            self.con = psycopg2.connect(**self.connection_config)
        except Exception as e:
            logging.exception("_connect failed")
            raise e
    

    def read(self, variable, start, end, config):
        """
        read data from db and store data in self
        """
        logging.info("reading %s from %s to %s", variable, start, end)

        self.variable = variable

        def _read():
            query = """
            SELECT * 
            FROM (
                SELECT 
                    timeutc, 
                    scal as """ + variable + """, 
                    CASE WHEN mode = 'General' THEN 0 ELSE 1 END as """ + variable + """_outlier 
                FROM """ + variable + """ 
                WHERE timeutc BETWEEN %(start)s AND %(end)s
            ) table_""" + variable

            for v in config["related"][variable]:
                query = query + """
                FULL JOIN (
                    SELECT 
                        timeutc, 
                        scal as """ + v + """ 
                    FROM """ + v + """
                    WHERE timeutc BETWEEN %(start)s AND %(end)s
                ) table_""" + v + """
                USING (timeutc)"""

            logging.debug("query: %s", query)

            params = {"table": variable, "start": start.isoformat(), "end": end.isoformat()}
            logging.debug("params: %s", params)

            self.data = pd.read_sql(query, self.con, params=params)
            
        try:
            _read()
        except Exception as e:
            logging.exception("read query failed. Reconnecting and Retrying...")
            self._connect()
            try:
                _read()
            except Exception as e:
                logging.exception("read query failed twice")
                raise ReadException(e)

        logging.debug("self.data %s", self.data)
        logging.debug("%s", self.data.dtypes)
        self.data = self.data.set_index("timeutc", drop=True).sort_index()


    def get_data(self, variable=None):
        """
        return data of given variable

        if variable is None, return data of all variables

        data has to be read before (using self.read)
        """
        if variable is None:
            return self.data
        
        return self.data[variable]
    
    def get_outliers(self):
        """
        return outliers for variable self.variable
        """
        return self.data.loc[self.data[self.variable + "_outlier"] == 1, self.variable]
    
    def write_outliers(self, outliers):
        """
        
        persist list of outliers in database and update self.data accordingly

        outliers is a list of datetime64 objects

        every element of outliers must be in self.data.index
        """
        def _write():
            if len(outliers) == 0:
                logging.info("no outliers to write to db")
            else:
                query = "UPDATE " + self.variable + " SET mode='Maintenance' WHERE timeutc IN (" + ", ".join(["'" + str(o) + "'" for o in outliers]) + ")"
                logging.debug("query %s", query)
                cur = self.con.cursor()
                cur.execute(query)
                self.con.commit()
                r = cur.rowcount
                logging.debug("write result %s", r)

        try:
            _write()
        except Exception as e:
            logging.exception("write query failed. Reconnecting and Retrying...")
            self._connect()
            try:
                _write()
            except Exception as e:
                logging.exception("write query failes twice")
                src.plot.Plot.get_instance().update_status("ERROR: Writing to Database failed!")

        self.data.loc[outliers, self.variable + "_outlier"] = 1