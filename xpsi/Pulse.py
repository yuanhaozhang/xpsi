from __future__ import division, print_function

__all__ = ["Pulse", "LikelihoodError"]

from .global_imports import *
from . import global_imports

from .Data import Data
from .Instrument import Instrument
from .Background import Background
from .Interstellar import Interstellar

from .tools.channel_integrator import channel_integrator
from .tools.energy_interpolator import energy_interpolator
from .tools.energy_adaptor import energy_adaptor
from .tools.phase_integrator import phase_integrator

from abc import abstractmethod
from .ParameterSubspace import ParameterSubspace

class LikelihoodError(xpsiError):
    """ Raised if there is a problem with the value of the log-likelihood. """

class Pulse(ParameterSubspace):
    """
    A pulse is constituted by some X-ray dataset, a model instrument
    with which that data was acquired, a model background, and an object for
    modelling interstellar processes.

    The methods in this class must transform incident specific flux pulsations
    into a structure congruent to that of the data for the purpose of
    evaluation of the likelihood.

    :param obj data: An instance of :class:`~.Data.Data`.

    :param obj instrument: An instance of :class:`~.Instrument.Instrument`.

    :param obj background:
        If not ``None``, an instance of :class:`~.Background.Background`.
        It is assumed if one constructs a model using instances of
        :class:`~.Background.Background` that the background needs to be
        folded through a model instrument. If ``None``, it is still possible
        for one to define and use background parameters in a custom subclass
        of :class:`Pulsation`. In particular, background parameters for some
        model which directly specifies background contribution in units of
        count/s per *output* channels. These background parameters can even
        *be* the counts/s in output channels.

    :param obj interstellar:
        If not ``None``, an instance of :class:`~.Interstellar.Interstellar`.
        To be applied to the incident source pulsation as a modifier callable.

    :param int energies_per_interval:
        The number of energies to compute photon fluxes, per input energy
        channel of the instrument.

    """
    def __init__(self,
                 data,
                 instrument,
                 background = None,
                 interstellar = None,
                 energies_per_interval = 0.25,
                 default_energy_spacing = 'logspace',
                 fast_rel_energies_per_interval = 0.5,
                 adaptive_energies = False,
                 adapt_exponent = 0.5,
                 store = False,
                 *args,
                 **kwargs):

        if not isinstance(data, Data):
            raise TypeError('Invalid type for a data object.')
        else:
            self._data = data

        if not isinstance(instrument, Instrument):
            raise TypeError('Invalid type for an instrument object.')
        else:
            self._instrument = instrument

        if background is not None:
            if not isinstance(background, Background):
                raise TypeError('Invalid type for a background object.')
            else:
                self._background = background
        else:
            self._background = None

        if interstellar is not None:
            if not isinstance(interstellar, Interstellar):
                raise TypeError('Invalid type for an interstellar object.')
            else:
                self._interstellar = interstellar
        else:
            self._interstellar = None

        self._construct_energy_array(energies_per_interval,
                                     default_energy_spacing)
        self._construct_fast_energy_array(fast_rel_energies_per_interval,
                                          default_energy_spacing)
        self.adaptive_energies = adaptive_energies
        self.adapt_exponent = adapt_exponent

        if not isinstance(store, bool):
            raise TypeError('Activate or deactivate caching with a boolean.')
        self._store = store

        # merge the subspaces; order unimportant
        super(Pulse, self).__init__(self._instrument,
                                    self._background,
                                    self._interstellar,
                                    *args, **kwargs)

    @property
    def background(self):
        """ Get the instance of :class:`~.Background.Background`."""
        return self._background

    @property
    def interstellar(self):
        """ Get the instance of :class:`~.Interstellar.Interstellar`."""
        return self._interstellar

    @property
    def instrument(self):
        """ Get the instance of :class:`~.Instrument.Instrument`."""
        return self._instrument

    def _construct_energy_array(self, energies_per_interval, default_spacing):
        """ Construct an array of photon energies for integration.

        This method will automatically construct an array of energies at which
        to integrate over a photosphere, given details about the contiguous
        subset of output channels the photon data spans (in an instance of
        the :class:`~.Data.Data` class) and the redistribution matrix of the
        model instrument (in an instance of the :class:`~.Instrument.Instrument`
        class).

        :param int energies_per_interval:
            The number of energies to compute photon fluxes, per input energy
            channel of the instrument.

        :raises IndexError:
            If the channel range of the data object is not consistent with
            the instrument object.

        """
        a, b = self._data.channel_range

        def search(i, j, k):
            while self._instrument.matrix[i,j] == 0.0:
                j += k
            return j

        a = search(a, 0, 1)
        b = self._instrument.matrix.shape[1] + search(b-1, -1, -1) + 1

        self._input_interval_range = (a, b)
        self._energy_edges = self._instrument.energy_edges[a:b + 1]

        self.set_energies(energies_per_interval, default_spacing)

    def _construct_fast_energy_array(self, rel_num, default_energy_spacing):
        if default_energy_spacing == 'linear':
            self.fast_energies = _np.linspace(self._energy_edges[0],
                                              self._energy_edges[-1],
                                              int(self._num_energies * rel_num))

        elif default_energy_spacing == 'logspace':
            self.fast_energies = _np.logspace(_np.log10(self._energy_edges[0]),
                                              _np.log10(self._energy_edges[-1]),
                                              int(self._num_energies * rel_num),
                                              base=10.0)
        else:
            raise ValueError('Invalid default energy spacing.')

    def set_energies(self, energies_per_interval, default_spacing):
        """ Set the energies for pulse integration. """

        n = self._input_interval_range[1] - self._input_interval_range[0]

        self._num_energies = int(energies_per_interval * n)

        if default_spacing == 'linear':
            self.default_energies = _np.linspace(self._energy_edges[0],
                                                  self._energy_edges[-1],
                                                  self._num_energies)
            self.logspace_energies = _np.logspace(_np.log10(self._energy_edges[0]),
                                                   _np.log10(self._energy_edges[-1]),
                                                   self._num_energies,
                                                   base=10.0)
        elif default_spacing == 'logspace':
            self.default_energies = _np.logspace(_np.log10(self._energy_edges[0]),
                                                   _np.log10(self._energy_edges[-1]),
                                                   self._num_energies,
                                                   base=10.0)
            self.logspace_energies = self.default_energies
        else:
            raise ValueError('Invalid default energy spacing.')

        self.logspace_energies_hires = _np.logspace(_np.log10(self._energy_edges[0]),
                                                    _np.log10(self._energy_edges[-1]),
                                                    self._num_energies * 10,
                                                    base=10.0)

    def _adapt_energies(self, signal, phases):
        """ Calculate a set of adapted energies for pulse integration. """
        signal = phase_integrator(1.0,
                                  _np.array([0.0,1.0]),
                                  signal,
                                  phases,
                                  0.0)

        energies = energy_adaptor((_np.log(10.0) * (self.fast_energies \
                                        * signal.reshape(-1))**(self.adapt_exponent)),
                                   _np.log10(self.fast_energies),
                                   self._num_energies)

        return 10.0**(energies)

    @property
    def fast_energies(self):
        return self._fast_energies

    @fast_energies.setter
    def fast_energies(self, energies):
        self._fast_energies = energies

    @property
    def default_energies(self):
        return self._default_energies

    @default_energies.setter
    def default_energies(self, obj):
        self._default_energies = obj

    @property
    def adaptive_energies(self):
        return self._adaptive_energies

    @adaptive_energies.setter
    def adaptive_energies(self, value):
        self._adaptive_energies = value

    @property
    def adapt_exponent(self):
        return self._adapt_exponent

    @adapt_exponent.setter
    def adapt_exponent(self, value):
        self._adapt_exponent = value

    @property
    def logspace_energies(self):
        return self._logspace_energies

    @logspace_energies.setter
    def logspace_energies(self, obj):
        self._logspace_energies = obj

    @property
    def logspace_energies_hires(self):
        return self._logspace_energies_hires

    @logspace_energies_hires.setter
    def logspace_energies_hires(self, obj):
        self._logspace_energies_hires = obj

    @property
    def energy_edges(self):
        """ Get a :class:`numpy.ndarray` of energy edges. """
        return self._energy_edges

    def fold(self, signals, fast_mode=False, threads=1):
        """ Fold a raw pulse signal through the response matrix.

        A :class:`numpy.ndarray` is stored as an instance attribute containing
        source pulsation for each *output* channel in units of counts cm^2/s
        (assuming instrument effective area units are cm^2).

        """
        if fast_mode:
            try:
                del self.energies
            except AttributeError:
                pass
            try:
                del self.fast_total_counts
            except AttributeError:
                pass

            if self.store:
                self._fast_incident_spectrum = []

            for hotRegion in signals:
                fast_total_counts = []
                energies = []

                for component, phases in zip(hotRegion, self.fast_phases):
                    if component is None:
                        energies.append(self.default_energies)
                        fast_total_counts.append(None)
                        if self.store:
                            self._fast_incident_spectrum.append(None)

                    else:
                        if self.adaptive_energies:
                            _ = self._adapt_energies(component, phases)
                            energies.append(_)
                        else:
                            energies.append(self.default_energies)

                        integrated = channel_integrator(threads,
                                                         component,
                                                         _np.log10(self.fast_energies),
                                                         _np.log10(self._energy_edges))

                        if self._interstellar is not None:
                            e = (self._energy_edges[:-1] + self._energy_edges[1:])/2.0
                            self._interstellar(e, integrated)

                        _ = self._instrument(integrated,
                                             self._input_interval_range,
                                             self._data.channel_range)

                        if self.store:
                            self._fast_incident_spectrum.append(_np.sum(_, axis=1))

                        fast_total_counts.append(_np.sum(_))

                self.energies = tuple(energies)
                self.fast_total_counts = tuple(fast_total_counts)
        else:
            try:
                del self.pulse
            except AttributeError:
                pass

            try:
                self.energies
            except AttributeError:
                for hotRegion in signals:
                    energies = []
                    for component in hotRegion:
                        energies.append(self.default_energies)
                    self.energies = tuple(energies)

            if self.store:
                try:
                    del self.raw_signals
                except AttributeError:
                    pass

                for hotRegion, hotRegion_energies in zip(signals, self.energies):
                    _ = energy_interpolator(1, hotRegion[0],
                                            _np.log10(hotRegion_energies[0]),
                                            _np.log10(self.logspace_energies_hires))

                    for component, component_energies in zip(hotRegion[1:], hotRegion_energies[1:]):
                        _ += energy_interpolator(1, component,
                                                 _np.log10(component_energies),
                                                 _np.log10(self.logspace_energies_hires))
                    self.raw_signals = _

                try:
                    del self.absorbed_raw_signals
                except AttributeError:
                    pass

                if self._interstellar is not None:
                    for signal in self.raw_signals:
                        self._interstellar.interp_and_absorb(self.logspace_energies_hires,
                                                             signal)

                        self.absorbed_raw_signals = signal
                else:
                    for signal in self.raw_signals:
                        self.absorbed_raw_signals = _np.copy(signal)

                try:
                    del self.raw_signals_energy_intervals
                except AttributeError:
                    pass

            for hotRegion, hotRegion_energies in zip(signals, self.energies):
                integrated = channel_integrator(threads,
                                                hotRegion[0],
                                                _np.log10(hotRegion_energies[0]),
                                                _np.log10(self._energy_edges))

                for component, component_energies in zip(hotRegion[1:], hotRegion_energies[1:]):
                    integrated += channel_integrator(threads,
                                                     component,
                                                     _np.log10(component_energies),
                                                     _np.log10(self._energy_edges))

                if self.store:
                    self.raw_signals_energy_intervals = integrated.copy()

                if self._interstellar is not None:
                    e = (self._energy_edges[:-1] + self._energy_edges[1:])/2.0
                    self._interstellar(e, integrated)

                self.pulse = self._instrument(integrated,
                                              self._input_interval_range,
                                              self._data.channel_range)

            if self._background is not None:
                try:
                    self._background(self._energy_edges,
                                     self._data.phases)
                except TypeError:
                    print('Error when evaluating the incident background.')
                    raise

                self._background.folded_background = \
                    self._instrument(self._background.background,
                                     self._input_interval_range,
                                     self._data.channel_range)

    @property
    def phases(self):
        return [phases.copy() for phases in self._phases]

    @phases.setter
    def phases(self, obj):
        if not isinstance(obj, list):
            obj = [obj]
        self._phases = obj

    @property
    def fast_phases(self):
        return [phases.copy() for phases in self._fast_phases]

    @fast_phases.setter
    def fast_phases(self, obj):
        if not isinstance(obj, list):
            obj = [obj]
        self._fast_phases = obj

    @property
    def energies(self):
        return tuple(tuple(E.copy() for E in arg) for arg in self._energies)

    @energies.setter
    def energies(self, obj):
        try:
            self._energies.append(obj)
        except AttributeError:
            self._energies = [obj]

    @energies.deleter
    def energies(self):
        del self._energies

    @property
    def fast_total_counts(self):
        return tuple(self._fast_total_counts)

    @fast_total_counts.setter
    def fast_total_counts(self, obj):
        try:
            self._fast_total_counts.append(obj)
        except AttributeError:
            self._fast_total_counts = [obj]

    @fast_total_counts.deleter
    def fast_total_counts(self):
        del self._fast_total_counts

    @property
    def store(self):
        return self._store

    @store.setter
    def store(self, value):
        if isinstance(value, bool):
            self._store = value
        else:
            raise ValueError('Pulse storage requires boolean activation.')

    @property
    def data(self):
        """ Get the stored data object. """
        return self._data

    @data.setter
    def data(self, data):
        """ Set the data object. """
        if isinstance(data, Data):
                self._data = data
        else:
            raise TypeError('The data object is of an invalid type.')

    @property
    def pulse(self):
        """ Get the stored channel-by-channel signal components. """
        return tuple(signal.copy() for signal in self._pulse)

    @pulse.setter
    def pulse(self, obj):
        try:
            self._pulse.append(obj)
        except AttributeError:
            self._pulse = [obj]

    @pulse.deleter
    def pulse(self):
        del self._pulse

    @property
    def raw_signals(self):
        """ Get the incident signal components. """
        return tuple(signal.copy() for signal in self._raw_signals)

    @raw_signals.setter
    def raw_signals(self, obj):
        try:
            self._raw_signals.append(obj)
        except AttributeError:
            self._raw_signals = [obj]

    @raw_signals.deleter
    def raw_signals(self):
        del self._raw_signals

    @property
    def absorbed_raw_signals(self):
        """ Get the incident absorbed signal components. """
        return tuple(signal.copy() for signal in self._absorbed_raw_signals)

    @absorbed_raw_signals.setter
    def absorbed_raw_signals(self, obj):
        try:
            self._absorbed_raw_signals.append(obj)
        except AttributeError:
            self._absorbed_raw_signals = [obj]

    @absorbed_raw_signals.deleter
    def absorbed_raw_signals(self):
        del self._absorbed_raw_signals

    @property
    def raw_signals_energy_intervals(self):
        """ Get the raw signal components integrated over energy intervals. """
        return tuple(signal.copy() for signal in self._raw_signals_energy_intervals)

    @raw_signals_energy_intervals.setter
    def raw_signals_energy_intervals(self, obj):
        try:
            self._raw_signals_energy_intervals.append(obj)
        except AttributeError:
            self._raw_signals_energy_intervals = [obj]

    @raw_signals_energy_intervals.deleter
    def raw_signals_energy_intervals(self):
        del self._raw_signals_energy_intervals

    @property
    def expected_counts(self):
        return self._expected_counts

    @expected_counts.setter
    def expected_counts(self, obj):
        self._expected_counts = obj

    @expected_counts.deleter
    def expected_counts(self):
        del self._expected_counts

    @property
    def shift(self):
        return self._shift

    @shift.setter
    def shift(self, values):
        if isinstance(values, _np.ndarray):
            self._shift = values
        else:
            raise TypeError('Store phase shift parameters as a 1D ndarray.')

    @shift.deleter
    def shift(self):
        del self._shift

    @property
    def background_signal(self):
        """ Get stored background. """
        return self._background_signal

    @background_signal.setter
    def background_signal(self, obj):
        if isinstance(obj, _np.ndarray):
            self._background_signal = obj

    @background_signal.deleter
    def background_signal(self):
        del self._background_signal

    @property
    def caching_targets(self):
        """ Get a dictionary of model objects for caching.

        Called by the post-processing module.

        :raises AttributeError:
            If a property is not set in methods of a subclass, or if the
            ``self.store`` property is not ``True``.

        """
        return {'shift': self.shift,
                'pulse': self.pulse,
                'expected_counts': self.expected_counts,
                'raw_signals': self.raw_signals,
                'absorbed_raw_signals': self.absorbed_raw_signals,
                'raw_signals_energy_intervals': self.raw_signals_energy_intervals,
                'background_signal': self.background_signal}

    @property
    def loglikelihood(self):
        """ Return the logarithm of the likelihood.

        :raises AttributeError: If property not set in methods of a subclass.

        """
        return self._loglikelihood

    @loglikelihood.setter
    def loglikelihood(self, ll):
        """ Check and store the logarithm of the likelihood. """

        if _np.isnan(ll):
            raise LikelihoodError('Log-likelihood is ``NaN``.')

        if not _np.isfinite(ll):
            self._loglikelihood = -_np.inf
        else:
            self._loglikelihood = ll

    @abstractmethod
    def __call__(self, phase_shifts, **kwargs):
        """ Compute the logarithm of the likelihood and store it as a property.

        :param iterable phase_shifts:
            Container of phase shift :class:`.~Parameter.Parameter` instances,
            one per hot region, communicated by the likelihood object from
            the star object. The order is equal to the order of the hot
            region objects stored in ``photosphere.hot.objects``.

        :param dict kwargs:
            The following keyword arguments may be accessed.

        :param int threads:
            Number of ``OpenMP`` threads to use for likelihood evaluation.
            This argument can be ignored if not required.

        :param float llzero:
            The minimum log-likelihood setting for MultiNest. Points whose
            log-likelihood is lower than this value are ignored.

        """

    def synthesise(self, phase_shifts, directory, *args, **kwargs):
        """ Synthesise pulsation data according to the generative model.

        :param list p: Model nuisance parameters (fast). The length of this
                       list will be equal to the ``total_params`` property.

        :param str directory: Path to directory in which to write synthetic
                              data. It is recommended that the ``tag`` ID of
                              the pulse appears in the filename.

        :param tuple args: If the pulse is not folded in the slow block, the
                           first argument is the photospheric pulse, which is
                           to be passed on to the fold method.
                           The slow parameters follow, in case required.

        """
        raise NotImplementedError('Cannot synthesise data.')
