import bokeh
import logging

from src.database import Database
from src.outlier import OutlierDetector
from src.plot import Plot



def ButtonCorrectOutlier():
    button = bokeh.models.Button(label='Mark as Outlier', width=100)


    def callback():
        
        plot = Plot.get_instance()

        logging.info("correcting outlier %s, %s", plot.get_selected_outlier(), plot.data.loc[plot.get_selected_outlier(), plot.VARIABLE])

        logging.info("self.table_outlier.source.data %s",plot.table_outlier.source.data)
        plot.table_outlier.source.stream({"timeutc": plot.get_selected_outlier(list=True), "scal": plot.data.loc[plot.get_selected_outlier(),plot.VARIABLE].values.tolist()})
        logging.info("self.table_outlier.source.data %s",plot.table_outlier.source.data)
        
        plot.set_selected_outlier(OutlierDetector.get_instance().get_next_outlier(plot.get_selected_outlier().max()))
        plot.plot_outlier()
        plot.set_plot_range()
        
        logging.info("shift down %s", plot.shift_down.start)


    button.on_click(callback)


    return button


        