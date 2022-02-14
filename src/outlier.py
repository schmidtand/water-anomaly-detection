import numpy as np
import pandas as pd
import logging
import pickle
import os
import sys

from src.database import Database



class OutlierDetector:

    instance = None

    def get_instance():
        return OutlierDetector.instance

    def __init__(self, data, variable, config):
        """
        load the outlier detection model, classify the given input data and store the lists of consecutive outliers in list self.outlier_groups
        """
        OutlierDetector.instance = self

        self.variable = variable

        self.first_datapoint = data.index[0]

        if variable not in config["outlier_detector"].keys():
            logging.error("no outlier detection found for %s", variable)
        
        outlier_detector = config["outlier_detector"][variable]

        if type(outlier_detector) is str:
            # if entry in config is str, treat the str as the file path of the model and load the model

            if getattr(sys, 'frozen', False):
                application_path = os.path.dirname(sys.executable)
            elif __file__:
                application_path = os.path.dirname(__file__)

            outlier_detector = os.path.join(application_path, outlier_detector)

            logging.info("application_path %s", application_path)
            logging.info("loading outlier detection from model %s (absolute path %s)", outlier_detector, os.path.abspath(os.path.join(outlier_detector)))
            if not os.path.exists(os.path.join(outlier_detector)): logging.warning("%s does not exist", os.path.abspath(os.path.join(outlier_detector)))
            with open(outlier_detector, "rb") as outlier_detector:
                outlier_detector = pickle.load(outlier_detector)
        elif type(outlier_detector) is dict:
            # if entry in config is dict, load a non-pretrained model according to the parameters in the dict
            logging.info("loading outlier detection model %s with parameters %s", outlier_detector["name"], outlier_detector["params"])
            import src.classifier
            if outlier_detector["name"] == "AdvancedThresholdClassifier":
                outlier_detector = src.classifier.AdvancedThresholdClassifier(variable, **outlier_detector["params"])
            elif outlier_detector["name"] == "AutocorrelationClassifier":
                outlier_detector = src.classifier.AdvancedAutocorrelationClassifier(variable, **outlier_detector["params"])
            elif outlier_detector["name"] == "AdvancedAutocorrelationClassifier":
                outlier_detector = src.classifier.AdvancedAutocorrelationClassifier(variable, **outlier_detector["params"])
        else:
            logging.error("not implemented")
            pass

        logging.info("outlier_detector %s", type(outlier_detector))
        
        outliers = outlier_detector.predict(data)


        self.outlier_groups = None
        outliers = np.where(outliers == 1)[0]
        for i, i_data in zip(range(len(outliers)), outliers):
            if self.outlier_groups is None:
                self.outlier_groups = [[np.datetime64(data.index[i_data], "ns")]]
            else: 
                self.outlier_groups[-1].append(np.datetime64(data.index[i_data], "ns"))
            
            if i+1 < len(outliers) and i_data+1 < outliers[i+1]:
                self.outlier_groups.append([])
        
        if self.outlier_groups == None:
            self.outlier_groups = []


        logging.info("found %s outliers in %s groups in %s observations", sum([len(g) for g in self.outlier_groups]), len(self.outlier_groups), len(data))

    
    def get_outliers(self):
        """
        return a list of all detected outliers
        """
        return [x for y in self.outlier_groups for x in y] # flatten list of lists of outliers

    
    def get_next_outlier(self, x_start=None):
        """
        return a list containing the next group of consecutive outliers after the given time
        """
        logging.info("next outlier after %s", x_start)

        outliers = [[o for o in group if o not in Database.get_instance().get_outliers()] for group in self.outlier_groups]
        outliers = [group for group in outliers if len(group) > 0]

        if len(outliers) == 0:
            logging.warning("no outliers found")
            return []#[np.datetime64(self.first_datapoint, "ns")]
        
        if x_start is not None:
            outliers_after_x_start = [group for group in outliers if group[0] > x_start]

            if len(outliers_after_x_start) > 0:
                logging.info("next outlier group %s", outliers_after_x_start[0])
                return outliers_after_x_start[0]
            
            logging.info("no outlier found after %s", x_start)

        logging.info("next outlier group %s", outliers[0])
        return outliers[0]
    
