#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The abacus wrapper
"""
from pathlib import Path
import os
import numpy as np
from scipy.linalg import eigh
from TB2J.utils import symbol_number_list
from TB2J.myTB import AbstractTB
from TB2J.abacus.abacus_api import read_HR_SR
from TB2J.abacus.orbital_api import parse_abacus_orbital
from TB2J.abacus.stru_api import read_abacus, read_abacus_out


class AbacusWrapper(AbstractTB):
    def __init__(self, HR, SR, Rlist, nbasis, nspin=1):
        self.R2kfactor = 2j * np.pi
        self.is_orthogonal = False
        self._name = "ABACUS"
        self._HR = HR
        self.SR = SR
        self.Rlist = Rlist
        self.nbasis = nbasis
        self.nspin = nspin
        self.norb = nbasis * nspin
        self._build_Rdict()

    @property
    def HR(self):
        return self._HR

    @HR.setter
    def set_HR(self, HR):
        self._HR = HR

    def _build_Rdict(self):
        if hasattr(self, "Rdict"):
            pass
        else:
            self.Rdict = {}
            for iR, R in enumerate(self.Rlist):
                self.Rdict[tuple(R)] = iR

    def get_hamR(self, R):
        return self.HR[self.Rdict[tuple(R)]]

    def gen_ham(self, k, convention=2):
        """
        generate hamiltonian matrix at k point.
        H_k( i, j)=\sum_R H_R(i, j)^phase.
        There are two conventions,
        first:
        phase =e^{ik(R+rj-ri)}. often better used for berry phase.
        second:
        phase= e^{ikR}. We use the first convention here.

        :param k: kpoint
        :param convention: 1 or 2.
        """
        Hk = np.zeros((self.nbasis, self.nbasis), dtype="complex")
        Sk = np.zeros((self.nbasis, self.nbasis), dtype="complex")
        if convention == 2:
            for iR, R in enumerate(self.Rlist):
                phase = np.exp(self.R2kfactor * np.dot(k, R))
                H = self.HR[iR] * phase
                # Hk += H + H.conjugate().T
                Hk += H
                S = self.SR[iR] * phase
                # Sk += S + S.conjugate().T
                Sk += S
                # Hk = (Hk + Hk.conj().T)/2
                # Sk = (Sk + Sk.conj().T)/2
        elif convention == 1:
            # TODO: implement the first convention (the r convention)
            raise NotImplementedError("convention 1 is not implemented yet.")
            pass
        else:
            raise ValueError("convention should be either 1 or 2.")
        return Hk, Sk

    def solve(self, k, convention=2):
        Hk, Sk = self.gen_ham(k, convention=convention)
        return eigh(Hk, Sk)

    def solve_all(self, kpts, convention=2):
        nk = len(kpts)
        evals = np.zeros((nk, self.nbasis), dtype=float)
        evecs = np.zeros((nk, self.nbasis, self.nbasis), dtype=complex)
        for ik, k in enumerate(kpts):
            evals[ik], evecs[ik] = self.solve(k, convention=convention)
        return evals, evecs

    def HSE_k(self, kpt, convention=2):
        H, S = self.gen_ham(tuple(kpt), convention=convention)
        evals, evecs = eigh(H, S)
        return H, S, evals, evecs

    def HS_and_eigen(self, kpts, convention=2):
        """
        calculate eigens for all kpoints.
        :param kpts: list of k points.
        """
        nk = len(kpts)
        hams = np.zeros((nk, self.nbasis, self.nbasis), dtype=complex)
        evals = np.zeros((nk, self.nbasis), dtype=float)
        evecs = np.zeros((nk, self.nbasis, self.nbasis), dtype=complex)
        for ik, k in enumerate(kpts):
            hams[ik], S, evals[ik], evecs[ik] = self.HSE_k(
                tuple(k), convention=convention
            )
        return hams, None, evals, evecs


class AbacusParser:
    def __init__(self, spin=None, outpath=None, binary=False):
        self.outpath = outpath
        if spin is None:
            self.spin = self.read_spin()
        else:
            self.spin = spin
        self.binary = binary
        # read the information
        self.read_atoms()
        self.efermi = self.read_efermi()
        self.read_basis()

    def read_spin(self):
        with open(str(Path(self.outpath) / "running_scf.log")) as myfile:
            for line in myfile:
                if line.strip().startswith("nspin"):
                    nspin = int(line.strip().split()[-1])
                    if nspin == 1:
                        return "non-polarized"
                    elif nspin == 2:
                        return "collinear"
                    elif nspin == 4:
                        return "noncollinear"
                    else:
                        raise ValueError("nspin should be either 1 or 4.")

    def read_atoms(self):
        path1 = str(Path(self.outpath) / "../STRU")
        path2 = str(Path(self.outpath) / "../Stru")
        if os.path.exists(path1):
            self.atoms = read_abacus(path1)
        elif os.path.exists(path2):
            self.atoms = read_abacus(path2)
        else:
            raise Exception("The STRU or Stru file cannot be found.")
        return self.atoms

    def read_basis(self):
        fname = str(Path(self.outpath) / "Orbital")
        self.basis = parse_abacus_orbital(fname)
        return self.basis

    def read_HSR_collinear(self, binary=None):
        p = Path(self.outpath)
        SR_filename = p / "data-SR-sparse_SPIN0.csr"
        HR_filename = [p / "data-HR-sparse_SPIN0.csr", p / "data-HR-sparse_SPIN1.csr"]
        nbasis, Rlist, HR_up, HR_dn, SR = read_HR_SR(
            nspin=2,
            binary=self.binary,
            HR_fileName=HR_filename,
            SR_fileName=SR_filename,
        )
        return nbasis, Rlist, HR_up, HR_dn, SR

    def Read_HSR_noncollinear(self, binary=None):
        p = Path(self.outpath)
        SR_filename = str(p / "data-SR-sparse_SPIN0.csr")
        HR_filename = str(p / "data-HR-sparse_SPIN0.csr")
        nbasis, Rlist, HR, SR = read_HR_SR(
            nspin=4,
            binary=self.binary,
            HR_fileName=HR_filename,
            SR_fileName=SR_filename,
        )
        return nbasis, Rlist, HR, SR

    def get_models(self):
        if self.spin == "collinear":
            nbasis, Rlist, HR_up, HR_dn, SR = self.read_HSR_collinear()
            model_up = AbacusWrapper(HR_up, SR, Rlist, nbasis, nspin=1)
            model_dn = AbacusWrapper(HR_dn, SR, Rlist, nbasis, nspin=1)
            model_up.efermi = self.efermi
            model_dn.efermi = self.efermi
            model_up.basis, model_dn.basis = self.get_basis()
            model_up.atoms = self.atoms
            model_dn.atoms = self.atoms
            return model_up, model_dn
        elif self.spin == "noncollinear":
            nbasis, Rlist, HR, SR = self.Read_HSR_noncollinear()
            model = AbacusWrapper(HR, SR, Rlist, nbasis, nspin=2)
            model.efermi = self.efermi
            model.basis = self.get_basis()
            model.atoms = self.atoms
            return model

    def read_efermi(self):
        """
        Reading the efermi from the scf log file.
        Search for the line EFERMI = xxxxx eV
        """
        fname = str(Path(self.outpath) / "running_scf.log")
        efermi = None
        with open(fname, "r") as myfile:
            for line in myfile:
                if "EFERMI" in line:
                    efermi = float(line.split()[2])
        if efermi is None:
            raise ValueError(f"EFERMI not found in the {str(fname)}  file.")
        return efermi

    def get_basis(self):
        slist = symbol_number_list(self.atoms)
        if self.spin == "collinear":
            basis_up = []
            basis_dn = []
            for b in self.basis:
                basis_up.append((slist[b.iatom], b.sym, "up"))
                basis_dn.append((slist[b.iatom], b.sym, "down"))
            return basis_up, basis_dn
        elif self.spin == "noncollinear":
            basis = []
            for b in self.basis:
                basis.append((slist[b.iatom], b.sym, "up"))
                basis.append((slist[b.iatom], b.sym, "down"))
            return basis


def test_abacus_wrapper_collinear():
    outpath = "/Users/hexu/projects/TB2J_abacus/abacus-tb2j-master/abacus_example/case_Fe/1_no_soc/OUT.Fe"
    parser = AbacusParser(outpath=outpath, spin=None, binary=False)
    atoms = parser.read_atoms()
    # atoms=parser.read_atoms_out()
    # parser.read_HSR_collinear()
    model_up, model_dn = parser.get_models()
    H, S, E, V = model_up.HSE_k([0, 0, 0])
    # print(H.shape)
    # print(H.diagonal().real)
    # print(model_up.get_HR0().diagonal().real)
    print(parser.efermi)


def test_abacus_wrapper_ncl():
    outpath = "/Users/hexu/projects/TB2J_abacus/abacus-tb2j-master/abacus_example/case_Fe/2_soc/OUT.Fe"

    parser = AbacusParser(outpath=outpath, spin=None, binary=False)
    atoms = parser.read_atoms()
    model = parser.get_models()
    H, S, E, V = model.HSE_k([0, 0, 0])
    print(parser.efermi)


if __name__ == "__main__":
    # test_abacus_wrapper()
    test_abacus_wrapper_ncl()
