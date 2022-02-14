import bokeh
import logging
from bokeh.plotting import figure
from bokeh.models import Rect
from bokeh.models.callbacks import CustomJS
from bokeh.events import Tap
import numpy as np

from src.database import Database
from src.outlier import OutlierDetector
from src.plot import Plot


def Figure(box_select_tool, pan_tool, y_scale="linear"):
    """
    create Figure object
    """

    plot = Plot.get_instance()

    fig = figure(
        x_axis_type='datetime', 
        x_range=plot.x_range,
        y_axis_label='',
        title="",
        active_scroll ="wheel_zoom",
        margin=(5,5,0,5),
        sizing_mode="stretch_both",
        **({"y_axis_type": "log", "y_range": [10e0, 10e4]} if y_scale == "log" else {"y_range": plot.y_range})
    )
    fig.toolbar.active_drag = box_select_tool
    fig.add_tools(box_select_tool)
    fig.add_tools(pan_tool)
    
    [fig.xaxis.formatter.__setattr__(a, "%d.%m.%Y, %H:%M") for a in ["years", "months", "days", "hours", "hourmin", "minutes"]]
    [fig.xaxis.formatter.__setattr__(a, "%d.%m.%Y, %H:%M:%S.%f") for a in ["minsec", "seconds", "milliseconds", "microseconds"]]


    # on MouseMove set value of python variable shift_down to value of js variable shift_down (see plot.html)
    # there is a periodic callback setting fig.toolbar.active_drag to box_select_tool or pan_tool accordingly
    fig.js_on_event(bokeh.events.MouseMove, CustomJS(args={"bokeh_shift_down": plot.shift_down}, code="""if (shift_down & bokeh_shift_down.start == 0) bokeh_shift_down.start = 1; else if (!shift_down & bokeh_shift_down.start == 1) bokeh_shift_down.start = 0;"""))



    # add PanStart, PanEnd events for selecting a data point by panning with the BoxSelectTool (only activated when shift_down):

    global pan_start_x, pan_start_y
    pan_start_x = None
    pan_start_y = None

    def pan_start(event):
        global pan_start_x, pan_start_y
        pan_start_x = np.datetime64(int(event.x)*10**6, 'ns')
        pan_start_y = event.y

    fig.on_event(bokeh.events.PanStart, pan_start)


    def pan_end(event):
        global pan_start_x, pan_start_y
        event_x = np.datetime64(int(event.x)*10**6, 'ns')
        
        # select data points inside area of BoxSelectTool:
        if event_x < pan_start_x:
            sel1 = plot.data.index.values < pan_start_x
            sel2 = plot.data.index > event_x
        else:
            sel1 = plot.data.index > pan_start_x
            sel2 = plot.data.index < event_x

        if event.y < pan_start_y:
            sel3 = plot.data[plot.VARIABLE] < pan_start_y
            sel4 = plot.data[plot.VARIABLE] > event.y
        else:
            sel3 = plot.data[plot.VARIABLE] > pan_start_y
            sel4 = plot.data[plot.VARIABLE] < event.y
        
        if len(plot.data.loc[sel1 & sel2 & sel3 & sel4]) > 0:
            plot.set_selected_outlier(plot.data.loc[sel1 & sel2 & sel3 & sel4].index.values)
            plot.plot_outlier()

        pan_start_x = None
        pan_start_y = None

    fig.on_event(bokeh.events.PanEnd, pan_end)

    fig.toolbar_location = None


    # stop animated scrolling when panning/zooming:

    def stop_scroll_animation(event):
        plot.x_range_aim = None
        plot.y_range_aim = None
    fig.on_event(bokeh.events.Pan, stop_scroll_animation)


    return fig


        




def MiniFigure(y_scale="linear"):

    plot = Plot.get_instance()

    mini_fig = figure(
        x_axis_type='datetime', 
        x_range=(plot.data.index.min() - 0.005 * (plot.data.index.max()-plot.data.index.min()), plot.data.index.max() + 0.005 * (plot.data.index.max()-plot.data.index.min())),
        y_axis_label='',
        title="",
        sizing_mode="stretch_width",
        plot_height=250,
        margin=(5,5,5,5),
        tools="",
        **({"y_axis_type": "log", "y_range": [1, 10**len(str(int(plot.data[plot.VARIABLE].max() + 0.075 * (plot.data[plot.VARIABLE].max()-plot.data[plot.VARIABLE].min()))))]} 
        if y_scale == "log" 
        else {"y_range": (plot.data[plot.VARIABLE].min() - 0.075 * (plot.data[plot.VARIABLE].max()-plot.data[plot.VARIABLE].min()), plot.data[plot.VARIABLE].max() + 0.075 * (plot.data[plot.VARIABLE].max()-plot.data[plot.VARIABLE].min()))})
    )
    
    def cb(event):

        event_x = np.datetime64(int(event.x)*10**6, "ns")
        x_range_start = np.datetime64(int(plot.x_range.start*10**6) if type(plot.x_range.start) is float else plot.x_range.start, 'ns')
        x_range_end = np.datetime64(int(plot.x_range.end*10**6) if type(plot.x_range.end) is float else plot.x_range.end, 'ns')

        plot.x_range.start = event_x - 0.5*(x_range_end - x_range_start)
        plot.x_range.end = event_x + 0.5*(x_range_end - x_range_start)
        
    mini_fig.on_event(bokeh.events.Pan, cb)

    
    mini_fig.line('timeutc', plot.VARIABLE, color="black", line_width=0.75, name=plot.config["names"][plot.VARIABLE], source=plot.source)
    mini_fig.toolbar_location = None
    plot.mini_rect = Rect(x=plot.x_range.start,y=plot.y_range.start, width=plot.x_range.end-plot.x_range.start, height=plot.y_range.end-plot.y_range.start, fill_color=None, line_width=0.5)
    mini_fig.add_glyph(plot.mini_rect)
    
    plot.mini_rect_x = Rect(
        y=0,
        x=plot.x_range.start,
        height=np.finfo(np.float16).max, 
        width=plot.x_range.end-plot.x_range.start,
        fill_alpha=0.1,
        fill_color="grey",
        line_color=None
    )
    mini_fig.add_glyph(plot.mini_rect_x)


    def click_mini_fig(event):
        logging.info("mini fig (%s, %s) clicked", event.x, event.y)

        x_range_start = np.datetime64(int(plot.x_range.start), "ms") if type(plot.x_range.start) is not np.datetime64 else plot.x_range.start
        x_range_end = np.datetime64(int(plot.x_range.end), "ms") if type(plot.x_range.end) is not np.datetime64 else plot.x_range.end
        
        r_x = x_range_end-x_range_start
        r_y = plot.y_range.end-plot.y_range.start

        logging.debug("x_range old: %s-%s", x_range_start, x_range_end)
        plot.x_range.start = np.datetime64(int(event.x), "ms") - r_x/2
        plot.x_range.end = np.datetime64(int(event.x), "ms") + r_x/2
        logging.debug("x_range new: %s-%s", plot.x_range.start, plot.x_range.end)

        logging.debug("y_range old: %s-%s", plot.y_range.start, plot.y_range.end)
        plot.y_range.start = event.y - r_y/2
        plot.y_range.end = event.y + r_y/2
        logging.debug("y_range new: %s-%s", plot.y_range.start, plot.y_range.end)

    mini_fig.on_event(Tap, click_mini_fig)

    return mini_fig
