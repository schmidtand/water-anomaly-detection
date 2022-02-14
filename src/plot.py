import bokeh
from bokeh.layouts import column, row
from bokeh.models import ColumnDataSource, Slider, CheckboxButtonGroup, Span, Button, RadioGroup, Toggle, WheelZoomTool, Range1d, Div, Rect, TextInput, DataTable, TableColumn, DateFormatter, Panel
from bokeh.core.properties import ColumnData
from bokeh.plotting import figure, show
from bokeh.server.server import Server
from bokeh.themes import Theme
from bokeh.models.renderers import GlyphRenderer
from bokeh.models.callbacks import CustomJS



from tornado.ioloop import IOLoop

import numpy as np
import logging
import datetime
import json

from src.database import Database
from src.outlier import OutlierDetector

def worker():
    server = Server({'/bkapp': Plot.plot}, io_loop=IOLoop(), allow_websocket_origin=["localhost:8000"])
    server.start()
    server.io_loop.start()



def get_script(variable, start, end, config):
    logging.info("script for %s, %s, %s, %s", variable, start, end, config)
    return bokeh.embed.server_document('http://localhost:5006/bkapp', arguments={"variable": variable, "start": start, "end": end, "config": config})


class Plot:
    """
    Control the visualization using bokeh objects
    """

    instance = None

    def __init__(self, config, data_start, data_end, variable):
        Plot.instance = self

        self.config = config
        self.VARIABLE = variable
        self.data_start = data_start
        self.data_end = data_end

        logging.info("initializing plot (VARIABLE %s, data_start %s, data_end %s)", self.VARIABLE, self.data_start, self.data_end)

        self.data = None
        self.source = None
        self.source_dict = None

        self.stats = None

        self.outlier_db = None
        self.outlier_db_mini = None
        self.outliers = None
        self.outliers_mini = None

        self.shift_down = Range1d()

        self.table_outlier = None
        self.create_table_outlier()

        self.variables = self.config["related"][self.VARIABLE]

        self.read_data()

        self.plot_stats()
        
        self.set_selected_outlier(OutlierDetector.get_instance().get_next_outlier())
        
        self.x_range = Range1d(start=np.datetime64(self.data.index.min(), "ns"), end=np.datetime64(self.data.index.max()))
        self.y_range = Range1d(start=self.data[self.VARIABLE].min(), end=self.data[self.VARIABLE].max())

        self.x_range_aim = None
        self.y_range_aim = None
        self.set_plot_range()

        self.box_select_tool = bokeh.models.BoxSelectTool()
        self.pan_tool = bokeh.models.PanTool()

        from src.figure import Figure, MiniFigure
        self.fig = Figure(self.box_select_tool, self.pan_tool, y_scale=self.config["y_scale"].get(self.VARIABLE, "linear"))
        self.mini_fig = MiniFigure(y_scale=self.config["y_scale"].get(self.VARIABLE, "linear"))

        def x_range_change(attr, old, new):
            """
            update the overview plot according to the cahanges in the main plot

            called when self.x_range changes (i.e. the visualized area in the x dimension of the main plot is changed e.g. by panning)
            """
            try:
                x_start = new if attr == "start" else self.x_range.start
                x_start = np.datetime64(int(x_start*10**6) if type(x_start) is float else x_start, 'ns')

                x_end = new if attr == "end" else self.x_range.end
                x_end = np.datetime64(int(x_end*10**6) if type(x_end) is float else x_end, 'ns')
            except Exception as e:
                logging.exception("attr %s, old %s, new %s", attr, old, new)
                raise e

            self.mini_rect.x = x_start + np.timedelta64(int(0.5*(x_end-x_start)/np.timedelta64(1,'s')), 's')
            self.mini_rect.width = abs(x_end-x_start)

            self.mini_rect_x.x = x_start + np.timedelta64(int(0.5*(x_end-x_start)/np.timedelta64(1,'s')), 's')
            self.mini_rect_x.width = abs(x_end-x_start)

        def y_range_change(attr, old, new):
            """
            update the overview plot according to the cahanges in the main plot

            called when self.y_range changes (i.e. the visualized area in the y dimension of the main plot is changed e.g. by panning)
            """
            y_start = new if attr == "start" else self.y_range.start
            y_end = new if attr == "end" else self.y_range.end
            self.mini_rect.y = y_start + 0.5*(y_end-y_start)
            self.mini_rect.height = abs(y_end-y_start)

        self.x_range.on_change('start', x_range_change)
        self.x_range.on_change('end', x_range_change)
        self.y_range.on_change('start', y_range_change)
        self.y_range.on_change('end', y_range_change)

        from src.button_correct_outlier import ButtonCorrectOutlier
        self.button_correct_outlier = ButtonCorrectOutlier()
        
        from src.button_next_outlier import ButtonNextOutlier
        self.button_next_outlier = ButtonNextOutlier()

        self.plot_lines()
        
        # create outlier plot
        self.outlier_circle = None
        self.outlier_spans = None

        self.div_status = Div(text="", height=20)
        self.status_end = None

    
    def get_instance():
        return Plot.instance











    def plot(doc):
        """
        add the generated bokeh objects to the javascript document

        called by the bokeh server
        """

        self = Plot.get_instance()
        
        self.plot_outlier()

        col = column(
            row(
                column(
                    Div(text="Marked Outliers:"), 
                    row(self.table_outlier, background="white", margin=(5,5,0,5)), 
                    row(self.button_remove_outlier, self.button_persist_outliers, sizing_mode="stretch_width"), 
                    self.stats
                ),
                column(
                    row(self.fig, sizing_mode="stretch_both"), 
                    self.mini_fig, 
                    row(
                        self.button_correct_outlier, 
                        self.button_next_outlier, align="center"), 
                    sizing_mode="stretch_width"
                    ),
                sizing_mode="stretch_height"
            ),
            self.div_status
        )

        col.sizing_mode="stretch_width"
        self.fig.sizing_mode="stretch_both"

        doc.add_root(col)

        doc.theme = Theme(json={
            "attrs": {
                "Figure": {
                    "background_fill_color": "#DDDDDD",
                    "outline_line_color": "white",
                    "toolbar_location": "above",
                    "height": 500,
                    "width": 800
                },
                "Grid": {
                    "grid_line_dash": [6, 4],
                    "grid_line_color": "white"
                },
                "CheckBoxButtonGroup": {
                    "flex-wrap": "wrap"
                }
            }
        })


        def scroll_animated():
            """
            check is self.x_range_aim (resp. self.y_range_aim) differ from self.x_range (resp. self.y_range). 
            If so self.self.x_range (resp. self.self.y_range) is changed slightly to closer match self.x_range_aim (resp. self.y_range_aim).
            As this callback function is called periodically oftenly, the animated scrolling through the visualization is achieved.
            """
            delta_coeff = 0.02

            if self.x_range_aim is None:
                return
            
            if type(self.x_range.start) is float:
                self.x_range.start = np.datetime64(int(self.x_range.start/1000), 's')

            if type(self.x_range.end) is float:
                self.x_range.end = np.datetime64(int(self.x_range.end/1000), 's')


            current_start = self.x_range.start
            current_end = self.x_range.end
            aim_start, aim_end = self.x_range_aim

            if aim_start < current_start or (aim_start > current_start and aim_end <= current_end):
                # scroll self.x_range.start
                delta = min(delta_coeff * (current_end-current_start), abs(aim_start-current_start))
                sign = 1 if aim_start > current_start else -1
                self.x_range.start += delta * sign
            
            if aim_end > current_end or (aim_end < current_end and aim_start >= current_start):
                # scroll self.x_range.end
                delta = min(delta_coeff * (current_end-current_start), abs(aim_end-current_end))
                sign = 1 if aim_end > current_end else -1
                self.x_range.end += delta * sign

            

            if self.y_range_aim is None:
                return

            current_start = self.y_range.start
            current_end = self.y_range.end
            aim_start, aim_end = self.y_range_aim

            if aim_start < current_start or (aim_start > current_start and aim_end <= current_end):
                # scroll self.y_range.start
                delta = min(delta_coeff * (current_end-current_start), abs(aim_start-current_start))
                sign = 1 if aim_start > current_start else -1
                self.y_range.start += delta * sign
            
            if aim_end > current_end or (aim_end < current_end and aim_start >= current_start):
                # scroll self.y_range.end
                delta = min(delta_coeff * (current_end-current_start), abs(aim_end-current_end))
                sign = 1 if aim_end > current_end else -1
                self.y_range.end += delta * sign

            if (self.x_range.start, self.x_range.end) == self.x_range_aim and (self.y_range.start, self.y_range.end) == self.y_range_aim:
                self.x_range_aim = None
                self.y_range_aim = None


        doc.add_periodic_callback(scroll_animated,25)

        def clear_status():
            if self.status_end is None:
                return
            if self.status_end < datetime.datetime.now():
                self.div_status.text = ""
                self.status_end = None
        doc.add_periodic_callback(clear_status, 100)



        def callback():
            """
            check if shift key is pressed. If so, switch between self.box_select_tool and self.pan_tool.
            """
            if self.shift_down.start == 1:
                if self.fig.toolbar.active_drag != self.box_select_tool:
                    logging.debug("shift down")
                    self.fig.toolbar.active_drag = self.box_select_tool

            elif self.shift_down.start == 0:
                if self.fig.toolbar.active_drag != self.pan_tool:
                    logging.debug("shift up")
                    self.fig.toolbar.active_drag = self.pan_tool

        doc.add_periodic_callback(callback, 100)




        self.fig.legend.location = "top_left"
        self.fig.legend.click_policy="hide"



    def update_status(self, text):
        self.div_status.text = text
        self.status_end = datetime.datetime.now() + datetime.timedelta(seconds=5)

    def set_selected_outlier(self, outlier_list):
        outlier_list2 = []
        for o in outlier_list:
            if type(o) is not np.datetime64 or o.dtype != np.datetime64(0, "ns"):
                logging.error("cannot select outlier at %s", o)
            else:
                outlier_list2.append(o)
        
        self._selected_outliers = np.array(outlier_list2, dtype=np.datetime64)

    def get_selected_outlier(self, list=False):
        if list: return [np.datetime64(i, "ns") for i in self._selected_outliers]
        return self._selected_outliers


    def set_plot_range(self):
        """
        set self.x_range_aim self.y_range_aim (see callback function scroll_animated) 
        """
        logging.info("set plot range")

        if len(self.get_selected_outlier()) == 0:
            return 


        # x axis:
        date_start = max((np.datetime64(self.get_selected_outlier().min()) - np.timedelta64(1, 'D')).astype("datetime64[ns]"), np.datetime64(self.data.index.min()).astype("datetime64[ns]"))
        date_end = min((np.datetime64(self.get_selected_outlier().max()) + np.timedelta64(1, 'D')).astype("datetime64[ns]"), np.datetime64(self.data.index.max()).astype("datetime64[ns]"))

        # y axis:
        values = self.data.loc[(self.data.index >= date_start) & (self.data.index <= date_end), self.VARIABLE]
        value_min = values.min() - 0.05*(values.max()-values.min())
        value_max = values.max() + 0.05*(values.max()-values.min())

        if False and self.x_range_aim is None:
            self.x_range.start = date_start
            self.x_range.end = date_end

        if False and self.y_range_aim is None:
            self.y_range.start = value_min
            self.y_range.end = value_max



        animated = True
        if animated:
            self.x_range_aim = date_start, date_end
            self.y_range_aim = value_min, value_max
        else:
            self.x_range.start = date_start
            self.x_range.end = date_end

            self.y_range.start = value_min
            self.y_range.end = value_max

        logging.info("setting x_range (%s, %s), y_range (%s, %s)", date_start, date_end, value_min, value_max)







    def plot_stats(self):
        outlier_db = Database.get_instance().get_outliers().index.values
        outliers = OutlierDetector.get_instance().get_outliers()

        self.stats = column(
            row(Div(text="{} anomalies suggested".format(len(outliers)))),
            row(Div(text="{} anomalies in database".format(len(outlier_db))))
        )








    def read_data(self):
        """
        read the data from src.database.Database and store it in a ColumnDataSource (= data structure needed for bokeh plots)
        """
        self.data = Database.get_instance().get_data([*self.config["related"][self.VARIABLE], self.VARIABLE])
        if self.source is not None:
            self.source.data = self.data
        else:
            self.source = ColumnDataSource(data=self.data)
        self.source_dict = self.source.data.copy()
        logging.info(self.source)






    def create_table_outlier(self):
        """
        create the table listing the selected outliers
        """

        source = ColumnDataSource(dict(
        timeutc=[],
        scal=[],
        ))

        columns = [
            TableColumn(field="timeutc", title="timeutc", formatter=DateFormatter(format="%Y-%m-%d %H:%M:%S")),
            TableColumn(field="scal", title="scal"),
        ]
        self.table_outlier = DataTable(source=source, columns=columns, width=250, height=300)


        self.button_remove_outlier = Button(label="Remove Selected", width=100)
        def button_remove_outlier_click():
            logging.info("remove %s %s %s", self.table_outlier.source.selected, self.table_outlier.source.selected.indices, self.table_outlier.source.selected.line_indices)
            indices = self.table_outlier.source.selected.indices
            self.table_outlier.source.data["timeutc"] = [x for i, x in enumerate(self.table_outlier.source.data['timeutc']) if i not in indices]
            self.table_outlier.source.data["scal"] = [x for i, x in enumerate(self.table_outlier.source.data['scal']) if i not in indices]
        self.button_remove_outlier.on_click(button_remove_outlier_click)

        def button_persist_outliers_click():
            outliers_to_persist = self.table_outlier.source.data["timeutc"]
            logging.info("persist outliers %s", outliers_to_persist)
            Database.get_instance().write_outliers(outliers_to_persist)

            self.table_outlier.source.data["timeutc"] = []
            self.table_outlier.source.data["scal"] = []
            
            self.outlier_db = None
            self.plot_outlier()


        self.button_persist_outliers = Button(label="Save", width=100)
        self.button_persist_outliers.on_click(button_persist_outliers_click)

    
    def plot_lines(self):
        """
        plot the displayed graphs in the main plot
        """
        line_main = self.fig.line('timeutc', self.VARIABLE, color="black", line_width=1.5, name=self.config["names"][self.VARIABLE], source=self.source, legend_label=self.config["names"][self.VARIABLE])
        lines = [
            self.fig.line('timeutc', var, color="gray", line_width=1, name=self.config["names"][var], source=ColumnDataSource(data=Database.get_instance().get_data([var]).dropna()), legend_label=self.config["names"][var], visible=False)
            for var 
            in self.variables
            if var != self.VARIABLE
        ]
        


    def plot_outlier(self):
        """
        plot detected outliers and outliers that were not detected (but are present in the database) in the main plot and in the overview plot

        called whenever the displayed outliers have to be updated
        """

        if self.outlier_circle is not None:
            self.fig.renderers.remove(self.outlier_circle)
            self.mini_fig.renderers.remove(self.outlier_circle_mini)
        
        outlier_db = Database.get_instance().get_outliers()
        outliers = OutlierDetector.get_instance().get_outliers()
        outlier_db_not_suggested = outlier_db.loc[[o for o in outlier_db.index.values if o not in outliers]]
        outlier_db_suggested = outlier_db.loc[[o for o in outlier_db.index.values if o in outliers]]
        suggested_not_in_outlier_db = np.array([o for o in outliers if o not in outlier_db.index.values])


        if self.outlier_db is not None:
            self.fig.renderers.remove(self.outlier_db[0])
            self.fig.renderers.remove(self.outlier_db[1])

        self.outlier_db = (
            self.fig.circle(outlier_db_not_suggested.index, outlier_db_not_suggested, size=20, color="red", alpha=0.5, legend_label="Marked as Anomaly in Database (not detected)"), 
            self.fig.circle(outlier_db_suggested.index, outlier_db_suggested, size=20, color="green", alpha=0.15, legend_label="Marked as Anomaly in Database (detected)")
        )
        self.outlier_db_mini = self.mini_fig.circle(outlier_db.index, outlier_db, size=10, color="red", alpha=0.15)


        if self.outliers is not None:
            self.fig.renderers.remove(self.outliers)
            self.mini_fig.renderers.remove(self.outliers_mini)
        
        logging.debug("self.get_selected_outlier() %s %s", suggested_not_in_outlier_db, self.get_selected_outlier())

        if len(suggested_not_in_outlier_db) == 0:
            self.outliers = None
            self.outliers_mini = None
        else:
            self.outliers = self.fig.circle(
                suggested_not_in_outlier_db[np.where(~np.isin(suggested_not_in_outlier_db, self.get_selected_outlier()))], 
                self.data.loc[suggested_not_in_outlier_db[np.where(~np.isin(suggested_not_in_outlier_db, self.get_selected_outlier()))], self.VARIABLE], 
                size=15, color="navy", alpha=0.5, legend_label="Detected Anomaly") 
            self.outliers_mini = self.mini_fig.circle(suggested_not_in_outlier_db[np.where(~np.isin(suggested_not_in_outlier_db, self.get_selected_outlier()))], self.data.loc[suggested_not_in_outlier_db[np.where(~np.isin(suggested_not_in_outlier_db, self.get_selected_outlier()))], self.VARIABLE], size=5, color="navy", alpha=0.15)

        self.outlier_circle = self.fig.circle(self.get_selected_outlier(), self.data.loc[self.get_selected_outlier(), self.VARIABLE], size=15, color="navy", alpha=1, legend_label="Selected") 
        self.outlier_circle_mini = self.mini_fig.circle(self.get_selected_outlier(), self.data.loc[self.get_selected_outlier(), self.VARIABLE], size=5, color="navy", alpha=0.25)


        if len(self.get_selected_outlier()) == 1:
            if self.outlier_spans is not None:
                if type(self.outlier_spans[0]) is Rect:
                    self.outlier_spans[0].visible = False
                    self.outlier_spans[1].visible = False
                else:
                    self.fig.renderers.remove(self.outlier_spans[0])
                    self.fig.renderers.remove(self.outlier_spans[1])
            self.outlier_spans = [
                Span(location=self.get_selected_outlier()[0], dimension='height', line_color='navy', line_dash='dashed', line_width=0.5, location_units="data"),
                Span(location=self.data.loc[self.get_selected_outlier()[0], self.VARIABLE], dimension='width', line_color='navy', line_dash='dashed', line_width=0.5, location_units="data")
            ]
            self.fig.renderers.extend(self.outlier_spans)
        elif len(self.get_selected_outlier()) > 1:
            # define (x, y, width, height) of vertical and horizontal Rect:
            rect_vertical = {
                "y": 0,
                "x": self.get_selected_outlier().min()+(self.get_selected_outlier().max()-self.get_selected_outlier().min())/2, 
                "height": np.finfo(np.float16).max, 
                "width": self.get_selected_outlier().max()-self.get_selected_outlier().min()
            }
            rect_horizontal = {
                "x": 0, 
                "y": self.data.loc[self.get_selected_outlier(), self.VARIABLE].min()+(self.data.loc[self.get_selected_outlier(), self.VARIABLE].max()-self.data.loc[self.get_selected_outlier(), self.VARIABLE].min())/2, 
                "width": np.iinfo(np.int64).max, 
                "height": self.data.loc[self.get_selected_outlier(), self.VARIABLE].max()-self.data.loc[self.get_selected_outlier(), self.VARIABLE].min()
            }
            if self.outlier_spans is not None and type(self.outlier_spans[0]) is Rect:
                # update Rects:
                self.outlier_spans[0].x = rect_vertical["x"]
                self.outlier_spans[0].y = rect_vertical["y"]
                self.outlier_spans[0].width = rect_vertical["width"]
                self.outlier_spans[0].height = rect_vertical["height"]
                self.outlier_spans[1].x = rect_horizontal["x"]
                self.outlier_spans[1].y = rect_horizontal["y"]
                self.outlier_spans[1].width = rect_horizontal["width"]
                self.outlier_spans[1].height = rect_horizontal["height"]
            else:
                if self.outlier_spans is not None:
                    self.fig.renderers.remove(self.outlier_spans[0])
                    self.fig.renderers.remove(self.outlier_spans[1])
                # create new Rects:
                self.outlier_spans = [
                    self.fig.rect(**rect_vertical, fill_color="gray", line_color=None, fill_alpha=0.2),
                    #Rect(y=0, x=self.get_selected_outlier().min()+(self.get_selected_outlier().max()-self.get_selected_outlier().min())/2, height=np.finfo(np.float64).max/2, width=self.get_selected_outlier().max()-self.get_selected_outlier().min(), line_color=None, fill_alpha=0.1)

                    self.fig.rect(**rect_horizontal, fill_color="gray", line_color=None, fill_alpha=0.2)
                    #Rect(y=self.data.loc[self.get_selected_outlier(), self.VARIABLE].min()+(self.data.loc[self.get_selected_outlier(), self.VARIABLE].max()-self.data.loc[self.get_selected_outlier(), self.VARIABLE].min())/2, x=self.get_selected_outlier().min()+(self.get_selected_outlier().max()-self.get_selected_outlier().min())/2, height=self.data.loc[self.get_selected_outlier(), self.VARIABLE].max()-self.data.loc[self.get_selected_outlier(), self.VARIABLE].min(), width=self.get_selected_outlier().max()-self.get_selected_outlier().min(), line_color=None, fill_alpha=0.1)
                ]

        self.fig.title.text = (
            (", ".join([str((np.datetime_as_string(o, unit="s"), self.data.loc[o, self.VARIABLE])) for o in self.get_selected_outlier()]) + " selected")
            if len(self.get_selected_outlier()) <= 3
            else (str(len(self.get_selected_outlier())) + " anomalies selected")
        )
    


    


