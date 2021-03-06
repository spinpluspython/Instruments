# -*- coding: utf-8 -*-
"""
Created on Nov 22 09:57:29 2017

@author: Steinn Ymir Agustsson

    Copyright (C) 2018 Steinn Ymir Agustsson, Vladimir Grigorev

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
import time

import h5py
import numpy as np
from PyQt5 import QtCore

from instruments import generic
from instruments.delaystage import DelayStage
from instruments.lockinamplifier import LockInAmplifier
from utilities.data import dict_to_hdf
from utilities.exceptions import RequirementError
from utilities.math import monotonically_increasing
from utilities.misc import iterate_ranges
from utilities.settings import parse_setting


class Experiment(QtCore.QObject):
    """ Experiment manager class.

    An object of this class is intended to control an experiment.

    This is done by adding to it instruments, via the :obj:add_instrument* method.

    A measurement session can be defined by adding parameter iterations.
    This is done by using the method `add_parameter_iteration`, which creates a
    tuple of 3 objects: the *instrument*, the *parameter* and *values*.
    **Instrument**: is an instance of the instrument which will be used to
    control this parameter.
    **parameter** is the name under which this parameter can be found in the
    instrument object instance
    **value** is a tuple or list of values. These are in order the values at
    which this parameter will be set. Each value will generate a measurement loop.

    This measurement loop can consist of multiple parameter iterations, meaning
    a measurement session can perform a measurement iterating over multiple
    parameters, resulting in n-dimensional measurements.

    Examples:
        # TODO: write some nice examples.
    Signals:
        finished (): at end of the scan. Bounced from worker.
        newData (): emitted at each measurement point.Bounced from worker.
            together with scan current_step information.
        stateChanged (str): emitted when the state of the worker changes.
            Allowed state values are defined in STATE_VALUES. Bounced from worker.

    """
    __TYPE = 'generic'
    # Signals
    finished = QtCore.pyqtSignal(dict)
    newData = QtCore.pyqtSignal(dict)
    progressChanged = QtCore.pyqtSignal(float)
    stateChanged = QtCore.pyqtSignal(str)

    def __init__(self, file=None, **kwargs):
        """ Create an instance of the Experiment

        This is initialized by creating adding all the passed arguments as
        instrument instances, and creates a list of names of them in
        self.instrument_list.
        Then, all methods which can be used to measure_avg some quantity and all
        parameters which can be set for each instruments are collected in
        self.measurable_methods and self.parameters respectively.

        self.measurable_methods is therefore a list of methods which can be
        directly called. These methods must have a test on the parent
        instrument being connected, or might fail.

        the class attribute *parameters* is a dictionary, where keys are the
        names of the instruments to which they belong. Each value is then a
        dictionary containing the name of the parameter as keys and a pointer
        to the parameter instance in the value.

        Args:
            file (:obj:str): file where to store experiment data. Defaults to
                :obj:None. If an existing file is passed, all settings stored
                in such file are loaded to the instance.
            kwargs (:obj:generic.Instrument): The names ofn given keyword
                arguments will be the specific name of the instrument
                (example: probe_stage) and the value must be an instance of the
                specific instrument (example: delaystage.NewportXPS)

        """
        super().__init__()
        self.logger = logging.getLogger('{}.Experiment'.format(__name__))
        self.logger.debug('created instance of Experiment')

        self.instrument_list = []
        self.parameters = {}
        self.required_instruments = None

        self.measurement_file = file
        self.measurement_name = 'unknown measurement ' + time.asctime().replace(':', '-')
        self.measurement_parameters = []
        self.measurement_settings = {}
        self.base_instruments = []
        # define which worker to use:
        self.worker = None

        if self.measurement_file is not None:
            self.logger.info('loading previous measurement file from {}'.format(self.measurement_file))
            self.load_settings_from_h5()
        for key, val in kwargs.items():
            try:
                self.add_instrument(key, val)
            except AssertionError:
                setattr(self, key, val)

    @property
    def name(self):
        """ return the name of the scan file
        """
        return self.measurement_name

    @name.setter
    def name(self, string):
        """ Change name of the measurement """
        self.measurement_name = string

    def add_parameter_iteration(self, name, unit, instrument, method, values):
        """ adds a measurement loop to the measurement plan.

        Args:
            instrument (generic.Instrument): instance of an instrument.
            parameter (str): method to be called to change the intended quantity
            values(:obj:list or :obj:tuple): list of parameters to be set, in
                the order in which they will be iterated.
        Raises:
            AssertionError: when any of the types are not respected.
        """
        assert isinstance(name, str), 'name must be a string'
        assert isinstance(unit, str), 'unit must be a string'
        assert isinstance(instrument, generic.Instrument), ' instrumnet must be instance of generic.Instrument'
        assert isinstance(method, str) and hasattr(instrument,
                                                   method), 'method should be a string representing the name of a method of the instrumnet class'
        assert isinstance(values, (list, tuple)), 'values should be list or tuple of numbers.'
        self.logger.info(
            'Added parameter iteration:\n\t- Instrument: {}\n\t- Method: {}\n\t- Values: {}'.format(instrument,
                                                                                                    method,
                                                                                                    values))
        self.measurement_parameters.append((name, unit, instrument, method, values))

    def check_requirements(self):
        """ check if the minimum requirements are fulfilled.

        Raises:
            RequirementError: if any requirement is not fulfilled.
        """
        try:
            missing = [x for x in self.required_instruments]
            for instrument in self.instrument_list:

                for i, inst_type in enumerate(self.required_instruments):
                    if isinstance(getattr(self, instrument), inst_type):
                        self.logger.info('found {} as {}'.format(instrument, inst_type))
                        self.base_instruments.append((instrument, getattr(self, instrument)))
                        missing.remove(inst_type)
                        break
            if len(missing) > 0:
                self.logger.error('RequirementError: no instrument of type {} present.'.format(missing))
                raise RequirementError('no instrument of type {} present.'.format(missing))
            elif not os.path.isfile(self.measurement_file):
                self.logger.error('FileNotFound : no File defined for this measurement.')
                raise FileNotFoundError('no File defined for this measurement.')
            else:
                print('all requrements met. Good to go!')
        except TypeError:
            print('No requirements set. Nothing to check!')

    def add_instrument(self, name, model, return_=True):
        """ Add an instrument to the experimental setup.

        adds as a class attribute an instance of a given model of an instrument,
        with a name of choice.

        This is intended to use by calling ExperimentalSetup.<instrument name>

        : parameters :
            name: str
                name to give to this specific instrument
            model: Instrument
                instance of the class corresponding to the model of this instrument
        """
        assert isinstance(model, generic.Instrument), '{} is not a recognized instrument type'.format(model)
        setattr(self, name, model)
        self.instrument_list.append(name)
        self.logger.info('Added {} as instance of {}'.format(name, model))
        if return_: return getattr(self, name)

    def print_setup(self):
        if len(self.instrument_list) == 0:
            print('No instruments loaded.')
        else:
            for name in self.instrument_list:
                print('{}: type:{}'.format(name, type(getattr(self, name))))

    def connect_all(self, *args):
        """ Connect to the instruments.

        Connects to all instruments, unless the name of one or multiple specific
        isntruments is passed, in which case it only connects to these.

        :parameters:
            *args: str
                name of the instrument(s) to be connected
        """
        if len(args) == 0:
            connect_list = tuple(self.instrument_list)
        else:
            connect_list = args
        for name in connect_list:
            self.logger.info('Attempting to connect to {}'.format(name))
            getattr(self, name).connect()

    def disconnect_all(self, *args):
        """ Connect to the instruments.

        Connects to all instruments, unless the name of one or multiple specific
        instruments is passed, in which case it only connects to these.

        :parameters:
            *args: str
                name of the instrument(s) to be connected
        """
        if len(args) == 0:
            disconnect_list = tuple(self.instrument_list)
        else:
            disconnect_list = args
        for name in disconnect_list:
            self.logger.info('Attempting to disconnect {}'.format(name))
            assert hasattr(self, name), 'No instrument named {} found.'.format(name)
            getattr(self, name).disconnect()

    def clear_instrument_list(self):
        """ Remove all instruments from the current instance."""
        self.disconnect_all()
        for inst in self.instrument_list:
            delattr(self, inst)
            self.logger.info('Removed {} from available instruments'.format(inst))
        self.instrument_list = []

    def start_measurement(self):
        """ start a measurement"""
        self.check_requirements()
        self.logger.debug('Creating Thread')
        self.scan_thread = QtCore.QThread()
        self.w = self.worker(self.measurement_file,
                             self.base_instruments,
                             self.measurement_parameters,
                             **self.measurement_settings)

        self.w.finished.connect(self.on_finished)
        self.w.newData.connect(self.on_newData)
        self.w.progressChanged[float].connect(self.on_progressChanged)
        self.w.stateChanged[str].connect(self.on_stateChanged)

        self.logger.debug('Thread initialized: moving to new thread')
        self.w.moveToThread(self.scan_thread)
        self.logger.debug('connecting')
        self.scan_thread.started.connect(self.w.project)
        self.logger.debug('starting')
        self.scan_thread.start()
        self.can_die = False
        self.logger.debug('main thread idle. waiting for thread death signal...')
        while not self.can_die:
            time.sleep(2)
        self.logger.debug('Thread death signal recieved. Main Thread waking up.')

    def create_file(self, name=None, dir=None, replace=True):
        """ Initialize a file for a measurement.

        :Structure:
            Each file will have 3 main groups (folders):
                **data**: where the dataframes will be stored
                **axes**: where the axes corresponding to the dataframes
                    dimensions will be stored
                **settings**: where the settings for each connected instruments
                    are saved.


        """
        if name is not None:
            self.measurement_name = name
        if dir is None:
            dir = parse_setting('paths', 'h5_data')
            if not os.path.isdir(dir):
                os.makedirs(dir)
        filename = os.path.join(dir, self.measurement_name)
        filename += '.h5'
        self.measurement_file = filename
        if os.path.isfile(filename) and replace:
            raise NameError('name already exists, please change.')
        else:
            self.logger.info('Created file {}'.format(filename))
            with h5py.File(filename, 'w', libver='latest') as f:
                rawdata_grp = f.create_group('raw_data')
                settings_grp = f.create_group('settings')
                axes_grp = f.create_group('axes')
                metadata_grp = f.create_group('metadata')

                # create a group for each instrument
                for inst_name in self.instrument_list:
                    inst_group = settings_grp.create_group(inst_name)
                    inst = getattr(self, inst_name)

                    # create a dataset for each parameter, and assign the current value.
                    for par_name, par_val in inst._settings.items():
                        try:
                            self.logger.info('getting attribute {} from {}'.format(par_name, inst))
                            data = getattr(inst, par_name)
                            inst_group.create_dataset(par_name, data=data)
                        except AttributeError:
                            self.logger.warning('attribute {} of {} not found'.format(par_name, inst))
                        except Exception as e:
                            self.logger.error('couldnt write setting to HDF5: {}'.format(e), exc_info=True)
                metadata_grp['date'] = time.asctime()
                metadata_grp['type'] = self.__TYPE
                self.logger.debug('Setup of file {} is complete'.format(filename))

    def load_settings_from_h5(self):
        raise NotImplementedError('cannot load settings yet... working on it!')  # TODO: implement load settings

    @QtCore.pyqtSlot(dict)
    def set_measurement_settings(self, settings_dict):  # TODO: this looks wrong.. needs checking!
        """ define the settings specific for the scan.

        Args:
            settings_dict: dictionary containing all the settings required to
                perform a scan.
                Keys must match those defined in self.scan_settings.
        """
        for key in self.measurement_settings:
            assert key in settings_dict, 'missing setting for {}'.format(key)
        self.measurement_settings = settings_dict

    @QtCore.pyqtSlot()
    def on_finished(self, signal):
        self.logger.info('SIGNAL: > finished < recieved')
        self.finished.emit(signal)
        self.can_die = True
        print('finished')

    @QtCore.pyqtSlot()
    def on_newData(self, signal):
        self.logger.info('SIGNAL: > newData < recieved')
        self.newData.emit(signal)

    @QtCore.pyqtSlot(float)
    def on_progressChanged(self, signal):
        self.logger.info('SIGNAL: > progressChanged < recieved')
        self.progressChanged.emit(signal)
        print('current_step: {}'.format(signal))

    @QtCore.pyqtSlot(str)
    def on_stateChanged(self, signal):
        self.logger.info('SIGNAL: > stateChanged < recieved')
        self.stateCanged.emit(signal)


class Worker(QtCore.QObject):
    """ Parent class for all workers.

    This class is to be launched and assigned to a thread.

    settings and instruments:
        these are the worker specific settings and instruments required to
        perform a measurement.

    signals emitted:
        finished (): at end of the scan.
        newData (): emitted at each measurement point.
            together with scan current_step information.
        stateChanged (str): emitted when the state of the worker changes.
            Allowed state values are defined in STATE_VALUES.
    """

    finished = QtCore.pyqtSignal()
    newData = QtCore.pyqtSignal()
    progressChanged = QtCore.pyqtSignal(float)
    stateChanged = QtCore.pyqtSignal(str)
    STATE_VALUES = ['loading', 'idle', 'changing parameters', 'running', 'failed', 'complete']
    __verbose = parse_setting('general', 'verbose')

    def __init__(self, file, base_instruments, parameters, **kwargs):  # ,**kwargs):
        """ Initialize worker instance.

        Args:
            file:
            base_instruments(:obj:tuple of :obj:str and :obj:generic.Instrument):
                name and instance of the main instruments required
            parameters (list of :obj:`generic.Parameter): parameters to be
                changed throughout this measurement session.
            disconnect_on_parameter_change (bool): if True, it connects and
                disconnects the required instrument every time a parameter needs
                to be set.
            **kwargs: all kwargs are passed as class attributes.
        """
        super().__init__()
        self.logger = logging.getLogger('{}.Worker'.format(__name__))
        self.logger.debug('Created a "Worker" instance')

        self.file = file
        for inst in base_instruments:
            setattr(self, inst[0], inst[1])
        self.names = []
        self.units = []
        self.instruments = []  # instruments which controls the parameters
        self.methods = []  # parameters to be changed
        self.values = []  # list of values at which to set the parameters

        for param in parameters:
            self.names.append(param[0])
            self.units.append(param[1])
            self.instruments.append(param[2])
            self.methods.append(param[3])
            self.values.append(param[4])

        for key, val in kwargs.items():
            setattr(self, key, val)

        # Flags
        self.__shouldStop = False  # soft stop, for interrupting at end of cycle.
        self.__state = 'none'
        self.current_index = None  # used to keep track of which parameter to change at each iteration
        self.current_step = 0  # keep track of the current_step of the scan
        self.n_of_steps = 0  # total number of steps of current_step to increment
        self.single_measurement_steps = 1  # number of steps in each measurement procedure

    @QtCore.pyqtSlot()
    def work(self):
        """ Iterate over all parameters and measure_avg.

        This method iterates over all values of the parameters and performs a
        measurement for each combination. The order defined will be maintained,
        and the effective result is taht of running a nested for loop with the
        first parameter being the outermost loop and the last, the innermost.

        :example:
        with
        parameter_methods = [set_temperature, set_polarization]
        parameter_values = [[10,20,30,40,50],[0,1,2,3]]
        will generate the equivalent of this loop:
        for temperature_values in parameter_values[0]:
            for polarization_values in parameter_values[1]:
                parameter_methods[0](temperature_values)
                parameter_methods[1](polarization_values)
                measure_avg()
        """
        self.logger.info('worker started working')
        if len(self.values) == 0:
            self.logger.info('No parameter loop: performing a single scan')
            self.measure()
        else:
            ranges = []
            self.__max_ranges = []

            for iter_vals in self.values:
                maxrange = len(iter_vals)
                ranges.append((0, maxrange))
                self.__max_ranges.append(maxrange)
            self.initialize_progress_counter()

            # initialize the indexes control variable
            self.current_index = [-1 for x in range(len(ranges))]
            self.logger.info('starting measurement loop!')
            for indexes in iterate_ranges(ranges):  # iterate over all parameters, and measure_avg
                if self.__shouldStop:
                    break
                print(indexes)
                self.set_parameters(indexes)
                self.measure()

        self.finished.emit()
        self.logger.info('Measurement loop completed')
        self.state = 'complete'

    def set_parameters(self, indexes):
        """ change the parameters to the corresponding index set.

        Leaves unchanged the parameter whose index hasn't changed on this iteration.

        Args:
            indexes (:obj:list of :obj:int): list of indexes of the parameter loops
            """
        self.state = 'changing parameters'
        self.logger.debug('Changing parameter')
        for i, index in enumerate(indexes):
            # if the index corresponding to the parameter i has changed in this
            # iteration, set the new parameter
            print(index, self.current_index)
            if index != self.current_index[i]:
                self.logger.info('setting parameters for iteration {}:'.format(indexes) +
                                 '\nchanging {}.{} to {}'.format(self.instruments[i], self.methods[i],
                                                                 self.values[i][index]))
                # now call the method of the instrument class with the value at#
                #  this iteration
                getattr(self.instruments[i], self.methods[i])(self.values[i][index])
                self.current_index[i] += 1

    def measure(self):
        """ Perform a measurement step.

        This method is called at every iteration of the measurement loop."""
        raise NotImplementedError("Method 'project' not implemented in worker (sub)class")

    def initialize_progress_counter(self):
        """ initialize the progress counter which helps keep track of measurement loop status"""
        self.n_of_steps = 1
        for i in self.__max_ranges:
            self.n_of_steps *= i
        self.n_of_steps *= self.single_measurement_steps
        self.logger.info('Progress Counter initialized: {} loop steps expected'.format(self.n_of_steps))

    def increment_progress_counter(self):
        self.current_step += 1
        self.progress = 100 * self.current_step / self.n_of_steps
        self.logger.debug(
            'Progress incremented to {}, step {}/{}'.format(self.progress, self.current_step, self.n_of_steps))

        self.progressChanged.emit(self.progress)

    @property
    def state(self):
        """ Get the current worker _state:

        Allowed States:
            loading: worker is setting up initial conditions.
            idle: ready to run, awaiting starting condition.
            running: obvious.
            error: worker stuck because of error or something.
        """
        return self.__state

    @state.setter
    def state(self, value):
        """ set new _state flag.

        Sets a new _state, emits a signal with the changed _state value.
        """
        assert value in self.STATE_VALUES, 'invalid status: {}'.format(value)
        self.__state = value
        self.stateChanged.emit(value)

    @QtCore.pyqtSlot(bool)
    def should_stop(self, flag):
        """ Soft stop, for interrupting at the end of the current cycle.

        For hard stop, use kill_worker slot.
        """
        self.logger.warning('Should_stop flag rised. The Worker will stop at the end of the current cycle.')
        self.__shouldStop = flag

    @QtCore.pyqtSlot()
    def kill_worker(self):
        """ Safely kill the thread by closing connection to all insturments.

        """
        self.logger.warning('Killing worker. Disconnecting all connected devices.')

        print('killing worker')
        for instrument in self.requiredInstruments:
            try:
                getattr(self, instrument).disconnect()
                print('closed connection to {}'.format(instrument))
            except AttributeError:
                pass
            except Exception as e:
                self.logger.error('Error killing {}: {}'.format(instrument, e), exc_info=True)


class FastScan(Experiment):
    __TYPE = 'stepscan'

    def __init__(self, file=None, **kwargs):
        super().__init__(file=file, **kwargs)
        self.logger = logging.getLogger('{}.StepScan'.format(__name__))
        self.logger.info('Created instance of StepScan.')

        self.required_instruments = []

        self.worker = FastScanWorker
        # define settings to pass to worker. these can be set as variables,
        # since they are class properties! see below...
        self.measurement_settings = {'averages': 2, 'time_zero': 0}

    @property
    def averages(self):
        return self.measurement_settings['averages']

    @averages.setter
    def averages(self, n):
        assert isinstance(n, int), 'cant run over non integer loops!'
        assert n > 0, 'cant run a negative number of loops!!'
        self.logger.info('Changed number of averages to {}'.format(n))
        self.measurement_settings['averages'] = n

    @property
    def time_zero(self):
        return self.measurement_settings['time_zero']

    @time_zero.setter
    def time_zero(self, t0):
        assert isinstance(t0, float) or isinstance(t0, int), 't0 must be a number!'
        self.logger.info('Changed time zero to {}'.format(t0))
        self.measurement_settings['time_zero'] = t0


class FastScanWorker(Worker):
    """ Subclass of Worker, designed to perform step scan measurements.

    Signals Emitted:

        finished (dict): at end of the scan, emits the results stored over the
            whole scan.
        newData (dict): emitted at each measurement point. Usually contains a
            dictionary with the last measured values toghether with scan
            current_step information.

    **Experiment Input required**:

    settings:
        stagePositions, lockinParametersToRead, dwelltime, numberOfScans
    instruments:
        lockin, stage

    """

    def __init__(self, file, base_instrument, parameters, **kwargs):
        super().__init__(file, base_instrument, parameters, **kwargs)
        self.logger = logging.getLogger('{}.Worker'.format(__name__))
        self.logger.debug('Created a "Worker" instance')

        self.check_requirements()
        self.single_measurement_steps = len(self.stage_positions) * self.averages
        self.parameters_to_measure = ['X', 'Y']
        self.logger.info('Initialized worker with single scan steps: {}'.format(self.single_measurement_steps))

    def check_requirements(self):
        assert hasattr(self, 'averages'), 'No number of averages was passed!'
        assert hasattr(self, 'time_zero'), 'Need to tell where time zero is!'

        self.logger.info('worker has all it needs. Ready to measure_avg!')

    def measure(self):
        """ Step Scan specific project procedure.

        Performs numberOfScans scans in which each moves the stage to the position defined in stagePositions, waits
        for the dwelltime, and finally records the values contained in lockinParameters from the Lock-in amplifier.
        """
        self.logger.info('---- New measurement started ----')

        groupname = 'raw_data/'
        for i, idx in enumerate(self.current_index):
            groupname += str(self.values[i][idx]) + self.units[i] + ' - '
        groupname = groupname[:-3]
        # with h5py.File(self.file, 'a') as f:
        #     f.create_group(groupname)


class StepScan(Experiment):
    __TYPE = 'stepscan'

    def __init__(self, file=None, **kwargs):
        super().__init__(file=file, **kwargs)
        self.logger = logging.getLogger('{}.StepScan'.format(__name__))
        self.logger.info('Created instance of StepScan.')

        self.required_instruments = [LockInAmplifier, DelayStage]

        self.worker = StepScanWorker
        # define settings to pass to worker. these can be set as variables,
        # since they are class properties! see below...
        self.measurement_settings = {'averages': 2,
                                     'stage_positions': np.linspace(-1, 3, 10),
                                     'time_zero': -.5,
                                     }

    @property
    def stage_positions(self):
        return self.measurement_settings['stage_positions']

    @stage_positions.setter
    def stage_positions(self, array):
        if isinstance(array, list):
            array = np.array(array)
        assert isinstance(array, np.ndarray), 'must be a 1d array'
        assert len(array.shape) == 1, 'must be a 1d array'
        assert monotonically_increasing(array), 'array must be monotonically increasing'
        max_resolution = 0
        for i in range(len(array) - 1):
            step = array[i + 1] - array[i]
            if step < max_resolution:
                max_resolution = step
        self.logger.info('Stage positions changed: {} steps'.format(len(array)))
        self.logger.debug(
            'Current stage_positions configuration: {} steps from {} to {} with max resolution {}'.format(len(array),
                                                                                                          array[0],
                                                                                                          array[-1],
                                                                                                          max_resolution))

        self.measurement_settings['stage_positions'] = array

    @property
    def averages(self):
        return self.measurement_settings['averages']

    @averages.setter
    def averages(self, n):
        assert isinstance(n, int), 'cant run over non integer loops!'
        assert n > 0, 'cant run a negative number of loops!!'
        self.logger.info('Changed number of averages to {}'.format(n))
        self.measurement_settings['averages'] = n

    @property
    def time_zero(self):
        return self.measurement_settings['time_zero']

    @time_zero.setter
    def time_zero(self, t0):
        assert isinstance(t0, float) or isinstance(t0, int), 't0 must be a number!'
        self.logger.info('Changed time zero to {}'.format(t0))
        self.measurement_settings['time_zero'] = t0


class StepScanWorker(Worker):
    """ Subclass of Worker, designed to perform step scan measurements.

    Signals Emitted:

        finished (dict): at end of the scan, emits the results stored over the
            whole scan.
        newData (dict): emitted at each measurement point. Usually contains a
            dictionary with the last measured values toghether with scan
            current_step information.

    **Experiment Input required**:

    settings:
        stagePositions, lockinParametersToRead, dwelltime, numberOfScans
    instruments:
        lockin, stage

    """

    def __init__(self, file, base_instrument, parameters, **kwargs):
        super().__init__(file, base_instrument, parameters, **kwargs)
        self.logger = logging.getLogger('{}.Worker'.format(__name__))
        self.logger.debug('Created a "Worker" instance')

        self.check_requirements()
        self.single_measurement_steps = len(self.stage_positions) * self.averages
        self.parameters_to_measure = ['X', 'Y']
        self.logger.info('Initialized worker with single scan steps: {}'.format(self.single_measurement_steps))

    def check_requirements(self):
        assert hasattr(self, 'averages'), 'No number of averages was passed!'
        assert hasattr(self, 'stage_positions'), 'no values of the stage positions were passed!'
        assert hasattr(self, 'time_zero'), 'Need to tell where time zero is!'
        assert hasattr(self, 'lockin'), 'No Lockin Amplifier found: attribute name should be "lockin"'
        assert hasattr(self, 'delay_stage'), 'No stage found: attribute name should be "delay_stage"'

        self.logger.info('worker has all it needs. Ready to measure_avg!')

    def measure(self):
        """ Step Scan specific project procedure.

        Performs numberOfScans scans in which each moves the stage to the position defined in stagePositions, waits
        for the dwelltime, and finally records the values contained in lockinParameters from the Lock-in amplifier.
        """
        self.logger.info('---- New measurement started ----')

        groupname = 'raw_data/'
        for i, idx in enumerate(self.current_index):
            groupname += str(self.values[i][idx]) + self.units[i] + ' - '
        groupname = groupname[:-3]
        # with h5py.File(self.file, 'a') as f:
        #     f.create_group(groupname)

        for avg_n in range(self.averages):
            self.lockin.connect()
            self.logger.info('scanning average n {}'.format(avg_n))
            d_avg = {}
            df_name = groupname + '/avg{}'.format(str(avg_n).zfill(4))
            for i, pos in enumerate(self.stage_positions):
                pos += self.time_zero
                self.delay_stage.move_absolute(pos)
                try:
                    real_pos = self.delay_stage.position  # TODO: implement, or remove
                except AttributeError:
                    self.logger.debug('No readout of stage position. saving with nominal value {}'.format(pos))
                    real_pos = pos

                result = self.lockin.measure(self.parameters_to_measure, return_dict=True)

                result['pos'] = pos
                result['real_pos'] = real_pos
                for k, v in result.items():
                    try:
                        d_avg[k].append(v)
                    except:
                        d_avg[k] = [v]
                self.logger.debug('Measured values: {}'.format(result))
                self.newData.emit()
                self.increment_progress_counter()
                self.logger.info(
                    'current_step: {:.3f}% step {} of {}'.format(self.progress, self.current_step, self.n_of_steps))
            dict_to_hdf(self.file, df_name, d_avg, self.parameters_to_measure, d_avg['pos'])
            self.logger.debug('writted data to file.')
            self.lockin.disconnect()

            #
            #
            # df = pd.DataFrame(data=d_avg, columns=self.parameters_to_measure, index=d_avg['pos'])
            # df.to_hdf(self.file, 'raw_data/' + df_name, mode='a', format='fixed')


if __name__ == "__main__":
    import os

    if os.getcwd()[-9] != 'FemtoScan':
        os.chdir('../')
    pass
