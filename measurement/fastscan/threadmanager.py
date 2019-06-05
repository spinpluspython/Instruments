# -*- coding: utf-8 -*-
"""

@author: Steinn Ymir Agustsson

    Copyright (C) 2018 Steinn Ymir Agustsson

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
import logging
import multiprocessing as mp
import os
import time

import h5py
import numpy as np
import xarray as xr
from PyQt5 import QtCore

from instruments.delaystage import StandaStage as DelayStage
from measurement.fastscan.processor import project, fit_autocorrelation
from measurement.fastscan.streamer import FastScanStreamer
from measurement.fastscan.threadpool import Runnable
from utilities.math import update_average
from utilities.settings import parse_setting, parse_category, write_setting


class FastScanThreadManager(QtCore.QObject):
    """
    This class manages the streamer processor and fitter workers for the fast
    scan data acquisition and processing.

    """
    newStreamerData = QtCore.pyqtSignal(np.ndarray)
    newProcessedData = QtCore.pyqtSignal(xr.DataArray)
    newFitResult = QtCore.pyqtSignal(dict)
    newAverage = QtCore.pyqtSignal(xr.DataArray)
    acquisitionStopped = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()
    newData = QtCore.pyqtSignal(np.ndarray)
    error = QtCore.pyqtSignal(Exception)

    def __init__(self):
        super().__init__()

        self.logger = logging.getLogger('{}.FastScanThreadManager'.format(__name__))
        self.logger.info('Created Thread Manager')

        self.__stream_queue = mp.Queue()  # Queue where to store unprocessed streamer data

        self.all_curves = None
        self.running_average = None
        self.streamer_average = None
        self.n_streamer_averages = 0

        self._calculate_autocorrelation = None
        self.should_stop = False
        self.streamerRunning = False

        self.delay_stage = DelayStage()

        self.timer = QtCore.QTimer()
        self.timer.setInterval(50.)
        self.timer.timeout.connect(self.on_timer)
        self.timer.start()
        self.counter = 0

        self.pool = QtCore.QThreadPool()
        self.pool.setMaxThreadCount(self.n_processors)

        self.create_streamer()

    def project(self, stream_data):
        runnable = Runnable(project, stream_data, self.dark_control,
                            self.shaker_position_step, self.shaker_ps_per_step)
        self.pool.start(runnable)
        runnable.signals.result.connect(self.on_processor_data)

    def fit_autocorrelation(self, da):
        runnable = Runnable(fit_autocorrelation, da, expected_pulse_duration=.1)
        self.pool.start(runnable)
        # runnable.signals.result.connect(self.on_fit_result)
        runnable.signals.result.connect(self.newFitResult.emit)

    def calibrate_shaker(self, iterations, integration):
        assert not self.streamerRunning, 'Cannot run Shaker calibration while streamer is running'

        import matplotlib.pyplot as plt
        from scipy.optimize import curve_fit

        # self.start_streamer()
        write_setting(0, 'fastscan - simulation', 'center_position')

        self.create_streamer()

        # stream = self.streamer.simulate_single_shot(integration)
        stream = self.streamer.measure_single_shot(integration)

        projected = project(stream, self.dark_control,
                            self.shaker_position_step, 0.05)
        min_ = projected.time.min()
        max_ = projected.time.max()
        print('\n - ')
        calib_positions_ = np.linspace(min_ * .7, max_ * .7, iterations // 2)
        calib_positions = np.concatenate((calib_positions_, calib_positions_[::-1]))
        centers = []
        # np.random.shuffle(calib_positions)
        for pos in calib_positions:
            print('\n - moving stage')

            self.delay_stage.move_absolute(pos)
            if parse_setting('fastscan', 'simulate'):
                write_setting(pos, 'fastscan - simulation', 'center_position')

            # stream = self.streamer.simulate_single_shot(integration)
            stream = self.streamer.measure_single_shot(integration)
            projected = project(stream, self.dark_control,
                                self.shaker_position_step, 1)
            res = fit_autocorrelation(projected)
            print('\n - fitted, result it: {}'.format(res['popt'][1]))
            centers.append(res['popt'][1])
            # plt.plot(projected)
        # plt.show()

        steps = []
        calib_steps = []
        print('\n - calculating shift')

        for i in range(len(centers) - 1):
            dy = np.abs(centers[i] - centers[i + 1])
            dx = np.abs(calib_positions[i] - calib_positions[i + 1])
            if dx != 0:
                steps.append(dy / dx)

        mean = np.mean(steps)
        std = np.std(steps)
        good_steps = [x for x in steps if (np.abs(x - mean) < 2 * std)]

        # correction_factor = np.mean(calib_steps)/np.mean(steps)

        # write_setting('fastscan', 'shaker_ps_per_step', pos)
        print('\n\n Shaker Calibration result: {} or {}'.format(1. / np.mean(steps), 1. / np.mean(good_steps)))

        def lin(x, a, b):
            return a * x + b

        # plt.plot(calib_positions, centers, 'ob')

        # try:
        popt_, pcov_ = curve_fit(lin, centers, calib_positions)

        cpos_fit = lin(np.array(centers), *popt_)
        calib_pos_good = []
        centers_good = []
        for i in range(len(centers)):
            std = np.std(calib_positions-cpos_fit)
            if np.abs(calib_positions[i]-cpos_fit[i]) < 1.2*std:
                calib_pos_good.append(calib_positions[i])
                centers_good.append(centers[i])
        popt, pcov = curve_fit(lin, centers_good, calib_pos_good)

        plt.plot(centers,calib_positions,'o')
        plt.plot(centers_good,calib_pos_good,'.')
        x = np.linspace(min(centers),max(centers),100)
        plt.plot(x, lin(x,*popt))
        # except:
        #     pass
        print('\n\n Shaker Calibration result:  {} | {}'.format(np.mean(good_steps), popt[0]))

        plt.show()

    @QtCore.pyqtSlot()
    def on_timer(self):
        """ For each idle processor, start evaluating an element in the streamer queue"""
        if self.should_stop:
            self.logger.debug('no data in queue, killing streamer')
            self.streamer_thread.exit()
            self.should_stop = False
            self.streamerRunning = False

        self.counter += 1

    def wait(self, n, timeout=1000):
        self.counter = 0
        i = 0
        while self.counter < n:
            i += 1
            if i > timeout:
                break

    def create_streamer(self):
        self.streamer_thread = QtCore.QThread()

        self.streamer = FastScanStreamer()
        self.streamer.newData[np.ndarray].connect(self.on_streamer_data)
        self.streamer.error.connect(self.error.emit)
        # self.streamer.finished.connect(self.on_streamer_finished)
        self.streamer.moveToThread(self.streamer_thread)
        self.streamer_thread.started.connect(self.streamer.start_acquisition)

    @QtCore.pyqtSlot()
    def start_streamer(self):
        self.should_stop = False
        self.streamerRunning = True
        self.create_streamer()
        self.streamer_thread.start()
        self.logger.info('FastScanStreamer started')
        self.logger.debug('streamer settings: {}'.format(parse_category('fastscan')))

    @QtCore.pyqtSlot()
    def stop_streamer(self):
        self.logger.debug('\n\nFastScan Streamer is stopping.\n\n')
        self.streamer.stop_acquisition()
        self.should_stop = True

    @QtCore.pyqtSlot(np.ndarray)
    def on_streamer_data(self, streamer_data):
        """ """
        self.newStreamerData.emit(streamer_data)
        if self.streamer_average is None:
            self.streamer_average = streamer_data
            self.n_streamer_averages = 1
        else:
            self.n_streamer_averages += 1
            self.streamer_average = update_average(streamer_data, self.streamer_average, self.n_streamer_averages)

        self.__stream_queue.put(streamer_data)
        self.logger.debug('added data to stream queue')
        self.project(self.__stream_queue.get())

    @QtCore.pyqtSlot(xr.DataArray)
    def on_processor_data(self, processed_dataarray):
        """ called when new processed data is available
        This emits data to the main window, so it can be plotted..."""

        self.newProcessedData.emit(processed_dataarray)

        t0 = time.time()
        if self.all_curves is None:
            self.all_curves = processed_dataarray
            self.running_average = processed_dataarray.dropna('time')

        else:
            self.all_curves = xr.concat([self.all_curves[-self.n_averages + 1:], processed_dataarray], 'avg')
            self.running_average = self.all_curves.mean('avg').dropna('time')

        self.newAverage.emit(self.running_average)

        self.logger.debug('calculated average in {:.2f} ms'.format((time.time() - t0) * 1000))

        if self._calculate_autocorrelation:
            self.fit_autocorrelation(self.running_average)

    @QtCore.pyqtSlot(dict)
    def on_fit_result(self, fitDict):
        self.newFitResult.emit(fitDict)

    @QtCore.pyqtSlot()
    def reset_data(self):
        # TODO: add popup check window
        self.running_average = None
        self.all_curves = None
        self.n_streamer_averages = None
        self.streamer_average = None

    def save_data(self, filename):
        if not '.h5' in filename:
            filename += '.h5'

        with h5py.File(filename, 'w') as f:
            f.create_dataset('/raw/avg', data=self.streamer_average)

            f.create_dataset('/all_data/data', data=self.all_curves.values)
            f.create_dataset('/all_data/time_axis', data=self.all_curves.time)
            f.create_dataset('/avg/data', data=self.running_average.values)
            f.create_dataset('/avg/time_axis', data=self.running_average.time)

            for k, v in parse_category('fastscan').items():
                if isinstance(v, bool):
                    f.create_dataset('/settings/{}'.format(k), data=v, dtype=bool)
                else:
                    f.create_dataset('/settings/{}'.format(k), data=v)

            # f.create_group('/settings')

    @QtCore.pyqtSlot()
    def close(self):
        self.stop_streamer()

    ### Properties

    @property
    def dark_control(self):
        return parse_setting('fastscan', 'dark_control')

    @dark_control.setter
    def dark_control(self, val):
        assert isinstance(val, bool), 'dark control must be boolean.'
        write_setting(val, 'fastscan', 'dark_control')

    @property
    def n_processors(self):
        return parse_setting('fastscan', 'n_processors')

    @n_processors.setter
    def n_processors(self, val):
        assert isinstance(val, int), 'dark control must be boolean.'
        assert val < os.cpu_count(), 'Too many processors, cant be more than cpu count: {}'.format(os.cpu_count())
        write_setting(val, 'fastscan', 'n_processors')
        self.create_processors()

    @property
    def n_averages(self):
        # try:
        #     return self._n_averages
        # except:
        #     self._n_averages = parse_setting('fastscan', 'n_averages')
        #     return self._n_averages
        return parse_setting('fastscan', 'n_averages')

    @n_averages.setter
    def n_averages(self, val):
        assert val > 0, 'cannot set below 1'
        write_setting(val, 'fastscan', 'n_averages')
        self._n_averages = val
        self.logger.debug('n_averages set to {}'.format(val))

    @property
    def n_samples(self):
        return parse_setting('fastscan', 'n_samples')

    @n_samples.setter
    def n_samples(self, val):
        assert val > 0, 'cannot set below 1'
        write_setting(val, 'fastscan', 'n_samples')
        self.logger.debug('n_samples set to {}'.format(val))

    @property
    def shaker_gain(self):
        return parse_setting('fastscan', 'shaker_gain')

    @shaker_gain.setter
    def shaker_gain(self, val):
        assert val in [1, 10, 100], 'gain can be 1,10,100 only'
        write_setting(val, 'fastscan', 'shaker_gain')
        self.logger.debug('n_samples set to {}'.format(val))

    @property
    def shaker_position_step(self):
        return parse_setting('fastscan', 'shaker_position_step')

    @property
    def shaker_ps_per_step(self):
        return parse_setting('fastscan', 'shaker_ps_per_step')

    @property
    def stage_position(self):
        return self.delay_stage.position_get()

    @stage_position.setter
    def stage_position(self, val):
        self.delay_stage.move_absolute(val)


if __name__ == '__main__':
    pass