
import bokeh
import logging

from src.outlier import OutlierDetector
from src.plot import Plot



def ButtonNextOutlier():
    button = bokeh.models.Button(label='Next Outlier', width=100)

    plot = Plot.get_instance()


    def callback():
        plot = Plot.get_instance()
        if len(plot.get_selected_outlier()) > 0:
            logging.info("next outlier after %s, %s", plot.get_selected_outlier(), plot.data.loc[plot.get_selected_outlier(), plot.VARIABLE])
            plot.set_selected_outlier(OutlierDetector.get_instance().get_next_outlier(plot.get_selected_outlier().max()))
            plot.plot_outlier()
            plot.set_plot_range()

    button.on_click(callback)


    return button
