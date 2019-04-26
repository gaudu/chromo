'''
Created on 19.01.2015

@author: afedynitch
'''

import numpy as np
from impy.common import MCRun, MCEvent, impy_config, pdata
from impy.util import standard_particles, info, AZ2pdg

_len_evt = 10000

class PYTHIA8Event(MCEvent):
    """Wrapper class around HEPEVT particle stack."""

    phep = np.zeros((5,_len_evt))
    vhep = np.zeros((4,_len_evt))
    jmohep = np.zeros((2,_len_evt))
    jdahep = np.zeros((2,_len_evt))
    status = np.zeros(_len_evt,dtype='int')
    p_ids = np.zeros(_len_evt,dtype='int')
    p_charge = np.zeros(_len_evt,dtype='int')
    n_events = 0
    def __init__(self, lib, event_kinematics, event_frame):
        # The following implementation is horrible and just a prototype
        # should move to fortran or C++ if performance issue
        self.n_events += 1
        nhep = 0
        for p in lib.event:
            self.status[nhep] = p.status()
            self.p_ids[nhep] = p.id()
            self.p_charge[nhep] = p.charge()
            self.vhep[:, nhep] = (p.xProd(),p.yProd(),p.zProd(), p.tProd())
            self.phep[:, nhep] = (p.px(),p.py(),p.pz(), p.e(), p.m())
            self.jmohep[:, nhep] = p.mother1(), p.mother2()
            self.jdahep[:, nhep] = p.daughter1(), p.daughter2()
            nhep += 1

        px, py, pz, en, m = self.phep
        vx, vy, vz, vt = self.vhep

        MCEvent.__init__(
            self,
            lib=lib,
            event_kinematics=event_kinematics,
            event_frame=event_frame,
            nevent=self.n_events,
            npart=nhep,
            p_ids=self.p_ids,
            status=self.status,
            px=px,
            py=py,
            pz=pz,
            en=en,
            m=m,
            vx=vx,
            vy=vy,
            vz=vz,
            vt=vt,
            pem_arr=self.phep,
            vt_arr=self.vhep)

    def filter_final_state(self):
        self.selection = np.where(self.status > 0)
        self._apply_slicing()

    def filter_final_state_charged(self):
        self.selection = np.where((self.status > 1) & (self.charge != 0))
        self._apply_slicing()

    @property
    def parents(self):
        if self._is_filtered:
            raise Exception(
                'Parent indices do not point to the' +
                ' proper particles if any slicing/filtering is applied.')
        return self.lib.hepevt.jmohep

    @property
    def children(self):
        if self._is_filtered:
            raise Exception(
                'Parent indices do not point to the' +
                ' proper particles if any slicing/filtering is applied.')
        return self.lib.hepevt.jdahep

    @property
    def charge(self):
        return self.p_charge[self.selection]

class PYTHIA8Run(MCRun):
    """Implements all abstract attributes of MCRun for the 
    EPOS-LHC series of event generators."""

    def sigma_inel(self):
        """Inelastic cross section according to current
        event setup (energy, projectile, target)"""
        # Cross section and energy (in mb and GeV)
        return self.lib.info.hiinfo.sigmaTot()

    def set_event_kinematics(self, event_kinematics):
        """Set new combination of energy, momentum, projectile
        and target combination for next event."""
        k = event_kinematics
        self._curr_event_kin = k

        # create new object
        self.lib = self.cpp_lib.Pythia() 
        # Replay initialization strings
        for param_string in self.save_init_strings:
            self.lib.readString(param_string)

        if k.A1 > 1 or k.A2 > 1:
            self.lib.readString("HeavyIon:SigFitNGen = 0")
            self.lib.readString(
                "HeavyIon:SigFitDefPar = 10.79,1.75,0.30,0.0,0.0,0.0,0.0,0.0")
        if k.A1 > 1:
            k.p1pdg = AZ2pdg(k.A1, k.A2)
            # pdgid, p name, ap name, spin, 3*charge, color, mass
            self.lib.particleData.addParticle(
                k.p1pdg, str(k.A1 * 100 + k.Z1),
                str(k.A1 * 100 + k.Z1) + 'bar', 1, 3 * k.Z1, 0, float(k.A1))
        if k.A2 > 1:
            k.p2pdg = AZ2pdg(k.A2, k.Z2)
            # pdgid, p name, ap name, spin, 3*charge, color, mass
            self.lib.particleData.addParticle(
                k.p2pdg, str(k.A2 * 100 + k.Z2),
                str(k.A2 * 100 + k.Z2) + 'bar', 1, 3 * k.Z2, 0, float(k.A2))

        self.lib.readString("Beams:idA = {0}".format(k.p1pdg))
        self.lib.readString("Beams:idB = {0}".format(k.p2pdg))
        self.lib.readString("Beams:eCM = {0}".format(k.ecm))
        # Set default stable
        self._define_default_fs_particles()

        self.lib.init()

        info(5, 'Setting event kinematics')

    def attach_log(self):
        """Routes the output to a file or the stdout."""
        # fname = impy_config['output_log']
        info(1, 'Not implemented at this stage')
        # if fname == 'stdout':
        #     lun = 6
        #     info(5, 'Output is routed to stdout.')
        # else:
        #     lun = self._attach_fortran_logfile(fname)
        #     info(5, 'Output is routed to', fname, 'via LUN', lun)

        # self.lib.pydat1.mstu[10] = lun

    def init_generator(self, event_kinematics, seed='random'):
        from random import randint

        self._abort_if_already_initialized()

        if seed == 'random':
            seed = randint(1000000, 10000000)
        else:
            seed = int(seed)
        info(5, 'Using seed:', seed)
        # Since a Pythia 8 instance is an object unlike in the case
        # of the Fortran stuff where the import of self.lib generates
        # the object, we will backup the library
        self.cpp_lib = self.lib
        # The object/instance is created each time event_kinematics is
        # set, since Pythia8 ATM does not support changing beams or
        # energies at runtime.
        # Super cool workaround but not very performant!

        self.save_init_strings = [
            "Random:setSeed = on",
            "Random:seed = " + str(seed),
            # Specify energy in center of mass
            "Beams:frameType = 1",
            # Minimum bias events
            "SoftQCD:all = on"
        ]

        # Add more options from config file
        for param_string in impy_config['pythia8']['options']:
            info(5, "Using Pythia 8 parameter:",param_string)
            self.save_init_strings.append(param_string)

        # self.set_event_kinematics(event_kinematics)

    def set_stable(self, pdgid, stable=True):
        if stable:
            self.lib.particleData.mayDecay(pdgid, False)
            info(5, 'defining', pdgid, 'as stable particle')
        else:
            self.lib.particleData.mayDecay(pdgid, True)
            info(5, pdgid, 'allowed to decay')

    def generate_event(self):
        return not self.lib.next()