# -*- coding: utf-8 -*-
from __future__ import with_statement
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from chemcoord._exceptions import PhysicalMeaning
from chemcoord._generic_classes.generic_core import GenericCore
from chemcoord.cartesian_coordinates._cartesian_class_pandas_wrapper import \
    PandasWrapper
from chemcoord.configuration import settings
from chemcoord.utilities import algebra_utilities
from chemcoord.utilities.set_utilities import pick
import chemcoord.constants as constants
import collections
from itertools import product
import numba as nb
from numba import jit
import numpy as np
import pandas as pd
from six.moves import zip  # pylint:disable=redefined-builtin
from sortedcontainers import SortedSet


class CartesianCore(PandasWrapper, GenericCore):

    _required_cols = frozenset({'atom', 'x', 'y', 'z'})
    _metadata_keys = frozenset([])

    # Look into the numpy manual for description of __array_priority__:
    # https://docs.scipy.org/doc/numpy-1.12.0/reference/arrays.classes.html
    __array_priority__ = 15.0

    # overwrites existing method
    def __init__(self, frame):
        """How to initialize a Cartesian instance.

        Args:
            frame (pd.DataFrame): A Dataframe with at least the
                columns ``['atom', 'x', 'y', 'z']``.
                Where ``'atom'`` is a string for the elementsymbol.

        Returns:
            Cartesian: A new cartesian instance.
        """
        if not isinstance(frame, pd.DataFrame):
            raise ValueError('Need a pd.DataFrame as input')
        if not self._required_cols <= set(frame.columns):
            raise PhysicalMeaning('There are columns missing for a '
                                  'meaningful description of a molecule')
        self._frame = frame.copy()
        self.metadata = {}
        self._metadata = {}

    def _return_appropiate_type(self, selected):
        if isinstance(selected, pd.Series):
            frame = pd.DataFrame(selected).T
            if self._required_cols <= set(frame.columns):
                selected = frame.apply(pd.to_numeric, errors='ignore')
            else:
                return selected

        if (isinstance(selected, pd.DataFrame)
                and self._required_cols <= set(selected.columns)):
            molecule = self.__class__(selected)
            molecule.metadata = self.metadata.copy()
            molecule._metadata = self._metadata.copy()
            return molecule
        else:
            return selected

    def _test_if_correctly_indexed(self, other):
        if not (set(self.index) == set(other.index)
                and np.alltrue(self['atom'] == other.loc[self.index, 'atom'])):
            message = ("You can add only Cartesians which are indexed in the "
                       "same way and use the same atoms.")
            raise PhysicalMeaning(message)

    def __add__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        if isinstance(other, CartesianCore):
            self._test_if_correctly_indexed(other)
            new.loc[:, coords] = self.loc[:, coords] + other.loc[:, coords]
        else:
            try:
                other = np.array(other, dtype='f8')
            except TypeError:
                pass
            new.loc[:, coords] = self.loc[:, coords] + other
        return new

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        if isinstance(other, CartesianCore):
            self._test_if_correctly_indexed(other)
            new.loc[:, coords] = self.loc[:, coords] - other.loc[:, coords]
        else:
            try:
                other = np.array(other, dtype='f8')
            except TypeError:
                pass
            new.loc[:, coords] = self.loc[:, coords] - other
        return new

    def __rsub__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        if isinstance(other, CartesianCore):
            self._test_if_correctly_indexed(other)
            new.loc[:, coords] = other.loc[:, coords] - self.loc[:, coords]
        else:
            try:
                other = np.array(other, dtype='f8')
            except TypeError:
                pass
            new.loc[:, coords] = other - self.loc[:, coords]
        return new

    def __mul__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        if isinstance(other, CartesianCore):
            self._test_if_correctly_indexed(other)
            new.loc[:, coords] = self.loc[:, coords] * other.loc[:, coords]
        else:
            try:
                other = np.array(other, dtype='f8')
            except TypeError:
                pass
            new.loc[:, coords] = self.loc[:, coords] * other
        return new

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        if isinstance(other, CartesianCore):
            self._test_if_correctly_indexed(other)
            new.loc[:, coords] = self.loc[:, coords] / other.loc[:, coords]
        else:
            try:
                other = np.array(other, dtype='f8')
            except TypeError:
                pass
            new.loc[:, coords] = self.loc[:, coords] / other
        return new

    def __rtruediv__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        if isinstance(other, CartesianCore):
            self._test_if_correctly_indexed(other)
            new.loc[:, coords] = other.loc[:, coords] / self.loc[:, coords]
        else:
            try:
                other = np.array(other, dtype='f8')
            except TypeError:
                pass
            new.loc[:, coords] = other / self.loc[:, coords]
        return new

    def __pos__(self):
        return self.copy()

    def __abs__(self):
        coords = ['x', 'y', 'z']
        new = self.copy()
        new.loc[:, coords] = abs(new.loc[:, coords])
        return new

    def __neg__(self):
        return -1 * self.copy()

    def __rmatmul__(self, other):
        coords = ['x', 'y', 'z']
        new = self.copy()
        new.loc[:, coords] = (np.dot(other, new.loc[:, coords].T)).T
        return new

    def __eq__(self, other):
        return self._frame == other._frame

    def append(self, other):
        # TODO(write Docstrign)
        new = self._frame.append(other._frame, verify_integrity=True)
        return self.__class__(new)

    def _to_ase_Atoms(self):
        import ase
        atoms = ''.join(self.loc[:, 'atom'])
        positions = self.loc[:, ['x', 'y', 'z']]
        # test
        return ase.Atoms(atoms, positions)

    def copy(self):
        molecule = self.__class__(self._frame)
        molecule.metadata = self.metadata.copy()
        molecule._metadata = self._metadata.copy()
        return molecule

    @staticmethod
    @jit(nopython=True)
    def _jit_give_bond_array(pos, bond_radii, self_bonding_allowed=False):
        """Calculate a boolean array where ``A[i,j] is True`` indicates a
        bond between the i-th and j-th atom.
        """
        n = pos.shape[0]
        bond_array = np.empty((n, n), dtype=nb.boolean)

        for i in range(n):
            for j in range(i, n):
                D = 0
                for h in range(3):
                    D += (pos[i, h] - pos[j, h])**2
                B = (bond_radii[i] + bond_radii[j])**2
                bond_array[i, j] = (B - D) >= 0
                bond_array[j, i] = bond_array[i, j]
        if not self_bonding_allowed:
            for i in range(n):
                bond_array[i, i] = False
        return bond_array

    def _update_bond_dict(self, fragment_indices,
                          positions,
                          bond_radii,
                          bond_dict=None,
                          self_bonding_allowed=False,
                          convert_index=None):
        """If bond_dict is provided, this function is not side effect free
        bond_dict has to be a collections.defaultdict(set)
        """
        assert (isinstance(bond_dict, collections.defaultdict)
                or bond_dict is None)
        fragment_indices = list(fragment_indices)
        if convert_index is None:
            convert_index = dict(enumerate(fragment_indices))
        if bond_dict is None:
            bond_dict = collections.defaultdict(set)

        frag_pos = positions[fragment_indices, :]
        frag_bond_radii = bond_radii[fragment_indices]

        bond_array = self._jit_give_bond_array(
            frag_pos, frag_bond_radii,
            self_bonding_allowed=self_bonding_allowed)
        a, b = bond_array.nonzero()
        a, b = [convert_index[i] for i in a], [convert_index[i] for i in b]
        for row, index in enumerate(a):
            # bond_dict is a collections.defaultdict(set)
            bond_dict[index].add(b[row])
        return bond_dict

    def _divide_et_impera(self, n_atoms_per_set=500, offset=3):
        coords = ['x', 'y', 'z']
        sorted_series = dict(zip(
            coords, [self[axis].sort_values() for axis in coords]))

        def ceil(x):
            return int(np.ceil(x))

        n_sets = len(self) / n_atoms_per_set
        n_sets_along_axis = ceil(n_sets**(1 / 3))
        n_atoms_per_set_along_axis = ceil(len(self) / n_sets_along_axis)

        def give_index(series, i, n_atoms_per_set_along_axis, offset=offset):
            N = n_atoms_per_set_along_axis
            try:
                min_value, max_value = series.iloc[[i * N, (i + 1) * N]]
            except IndexError:
                min_value, max_value = series.iloc[[i * N, -1]]
            selection = series.between(min_value - offset, max_value + offset)
            return set(series[selection].index)

        indices_at_axis = {axis: {} for axis in coords}
        for axis, i in product(coords, range(n_sets_along_axis)):
            indices_at_axis[axis][i] = give_index(sorted_series[axis], i,
                                                  n_atoms_per_set_along_axis)

        array_of_fragments = np.full([n_sets_along_axis] * 3, None, dtype='O')
        for i, j, k in product(*[range(x) for x in array_of_fragments.shape]):
            selection = (indices_at_axis['x'][i]
                         & indices_at_axis['y'][j]
                         & indices_at_axis['z'][k])
            array_of_fragments[i, j, k] = selection
        return array_of_fragments

    def get_bonds(self,
                  self_bonding_allowed=False,
                  offset=3,
                  modified_properties=None,
                  use_lookup=False,
                  set_lookup=True,
                  atomic_radius_data=settings['defaults']['atomic_radius_data']
                  ):
        """Return a dictionary representing the bonds.

        .. warning:: This function is **not sideeffect free**, since it
            assigns the output to a variable ``self._metadata['bond_dict']`` if
            ``set_lookup`` is ``True`` (which is the default). This is
            necessary for performance reasons.

        ``.get_bonds()`` will use or not use a lookup
        depending on ``use_lookup``. Greatly increases performance if
        True, but could introduce bugs in certain situations.

        Just imagine a situation where the ``Cartesian`` is
        changed manually. If you apply lateron a method e.g. ``to_zmat()``
        that makes use of ``get_bonds()`` the dictionary of the bonds
        may not represent the actual situation anymore.

        You have two possibilities to cope with this problem.
        Either you just re-execute ``get_bonds`` on your specific instance,
        or you change the ``internally_use_lookup`` option in the settings.
        Please note that the internal use of the lookup variable
        greatly improves performance.

        Args:
            modified_properties (dic): If you want to change the van der
                Vaals radius of one or more specific atoms, pass a
                dictionary that looks like::

                    modified_properties = {index1: 1.5}

                For global changes use the constants module.
            offset (float):
            use_lookup (bool):
            set_lookup (bool):
            self_bonding_allowed (bool):
            atomic_radius_data (str): Defines which column of
                :attr:`constants.elements` is used. The default is
                ``atomic_radius_cc`` and can be changed with
                :attr:`settings['defaults']['atomic_radius_data']`.
                Compare with :func:`add_data`.

        Returns:
            dict: Dictionary mapping from an atom index to the set of
            indices of atoms bonded to.
        """
        def complete_calculation():
            old_index = self.index
            self.index = range(len(self))
            fragments = self._divide_et_impera(offset=offset)
            positions = np.array(self.loc[:, ['x', 'y', 'z']], order='F')
            data = self.add_data([atomic_radius_data, 'valency'])
            bond_radii = data[atomic_radius_data]
            if modified_properties is not None:
                bond_radii.update(pd.Series(modified_properties))
            bond_radii = bond_radii.values
            bond_dict = collections.defaultdict(set)
            for i, j, k in product(*[range(x) for x in fragments.shape]):
                # The following call is not side effect free and changes
                # bond_dict
                self._update_bond_dict(
                    fragments[i, j, k], positions, bond_radii,
                    bond_dict=bond_dict,
                    self_bonding_allowed=self_bonding_allowed)

            for i in set(self.index) - set(bond_dict.keys()):
                bond_dict[i] = {}

            self.index = old_index
            rename = dict(enumerate(self.index))
            bond_dict = {rename[key]: {rename[i] for i in bond_dict[key]}
                         for key in bond_dict}
            return bond_dict

        if use_lookup:
            try:
                bond_dict = self._metadata['bond_dict']
            except KeyError:
                bond_dict = complete_calculation()
        else:
            bond_dict = complete_calculation()

        if set_lookup:
            self._metadata['bond_dict'] = bond_dict
        return bond_dict

    def _give_val_sorted_bond_dict(self, use_lookup):
        def complete_calculation():
            bond_dict = self.get_bonds(use_lookup=use_lookup)
            valency = dict(zip(self.index,
                               self.add_data('valency')['valency']))
            val_bond_dict = {key:
                             SortedSet([i for i in bond_dict[key]],
                                       key=lambda x: -valency[x], load=20)
                             for key in bond_dict}
            return val_bond_dict
        if use_lookup:
            try:
                val_bond_dict = self._metadata['val_bond_dict']
            except KeyError:
                val_bond_dict = complete_calculation()
        else:
            val_bond_dict = complete_calculation()
        self._metadata['val_bond_dict'] = val_bond_dict
        return val_bond_dict

    def give_coordination_sphere(
            self, index_of_atom, n_sphere=1, give_only_index=False,
            use_lookup=settings['defaults']['use_lookup']):
        """Return a Cartesian of atoms in the n-th coordination sphere.

        Connected means that a path along covalent bonds exists.

        Args:
            index_of_atom (int):
            give_only_index (bool): If ``True`` a set of indices is
                returned. Otherwise a new Cartesian instance.
            n_sphere (int): Determines the number of the coordination sphere.
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            A set of indices or a new Cartesian instance.
        """
        bond_dict = self.get_bonds(use_lookup=use_lookup)
        i = index_of_atom
        visited = set([i])
        try:
            tmp_bond_dict = {j: (bond_dict[j] - visited) for j in bond_dict[i]}
        except KeyError:
            tmp_bond_dict = {}
        n = 0
        while tmp_bond_dict and (n + 1) < n_sphere:
            new_tmp_bond_dict = {}
            for i in tmp_bond_dict:
                if i in visited:
                    continue
                visited.add(i)
                for j in tmp_bond_dict[i]:
                    new_tmp_bond_dict[j] = bond_dict[j] - visited
            tmp_bond_dict = new_tmp_bond_dict
            n += 1
        if give_only_index:
            return set(tmp_bond_dict.keys())
        else:
            return self.loc[set(tmp_bond_dict.keys())]

    def connected_to(
            self, index_of_atom, n_sphere=float('inf'), give_only_index=False,
            exclude=None, use_lookup=settings['defaults']['use_lookup']):
        """Return a Cartesian of atoms connected to the specified one.

        Connected means that a path along covalent bonds exists.

        Args:
            index_of_atom (int):
            give_only_index (bool): If ``True`` a set of indices is
                returned. Otherwise a new Cartesian instance.
            exclude (set): A set of indices that should be ignored
                for the path finding.
            n_sphere (int): Determines a maximum number
                for the coordination sphere.
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            A set of indices or a new Cartesian instance.
        """
        exclude = set() if exclude is None else exclude
        bond_dict = self.get_bonds(use_lookup=use_lookup)
        i = index_of_atom
        visited = set([i]) | exclude
        try:
            tmp_bond_dict = {j: (bond_dict[j] - visited) for j in bond_dict[i]}
        except KeyError:
            tmp_bond_dict = {}
        n = 0
        while tmp_bond_dict and (n) < n_sphere:
            new_tmp_bond_dict = {}
            for i in tmp_bond_dict:
                if i in visited:
                    continue
                visited.add(i)
                for j in tmp_bond_dict[i]:
                    new_tmp_bond_dict[j] = bond_dict[j] - visited
            tmp_bond_dict = new_tmp_bond_dict
            n += 1
        if give_only_index:
            return visited - exclude
        else:
            return self.loc[visited - exclude]

    def _preserve_bonds(self, sliced_cartesian,
                        use_lookup=settings['defaults']['use_lookup']):
        """Is called after cutting geometric shapes.

        If you want to change the rules how bonds are preserved, when
            applying e.g. :meth:`Cartesian.cutsphere` this is the
            function you have to modify.
        It is recommended to inherit from the Cartesian class to
            tailor it for your project, instead of modifying the
            source code of ChemCoord.

        Args:
            sliced_frame (Cartesian):
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            Cartesian:
        """
        included_atoms_set = set(sliced_cartesian.index)
        assert included_atoms_set.issubset(set(self.index)), \
            'The sliced Cartesian has to be a subset of the bigger frame'
        bond_dic = self.get_bonds(use_lookup=use_lookup)
        new_atoms = set([])
        for atom in included_atoms_set:
            new_atoms = new_atoms | bond_dic[atom]
        new_atoms = new_atoms - included_atoms_set
        while not new_atoms == set([]):
            index_of_interest = new_atoms.pop()
            included_atoms_set = (
                included_atoms_set |
                self.connected_to(
                    index_of_interest,
                    exclude=included_atoms_set,
                    give_only_index=True,
                    use_lookup=use_lookup))
            new_atoms = new_atoms - included_atoms_set
        molecule = self.loc[included_atoms_set, :]
        return molecule

    def cutsphere(
            self,
            radius=15.,
            origin=None,
            outside_sliced=True,
            preserve_bonds=False):
        """Cut a sphere specified by origin and radius.

        Args:
            radius (float):
            origin (list): Please note that you can also pass an
                integer. In this case it is interpreted as the
                index of the atom which is taken as origin.
            outside_sliced (bool): Atoms outside/inside the sphere
                are cut out.
            preserve_bonds (bool): Do not cut covalent bonds.

        Returns:
            Cartesian:
        """
        if origin is None:
            origin = np.zeros(3)
        elif pd.api.types.is_list_like(origin):
            origin = np.array(origin)
        else:
            origin = self.loc[origin, ['x', 'y', 'z']]

        molecule = self.distance_to(origin)
        if outside_sliced:
            molecule = molecule[molecule['distance'] < radius]
        else:
            molecule = molecule[molecule['distance'] > radius]

        if preserve_bonds:
            molecule = self._preserve_bonds(molecule)

        return molecule

    def cutcuboid(
            self,
            a=20,
            b=None,
            c=None,
            origin=None,
            outside_sliced=True,
            preserve_bonds=False):
        """Cut a cuboid specified by edge and radius.

        Args:
            a (float): Value of the a edge.
            b (float): Value of the b edge. Takes value of a if None.
            c (float): Value of the c edge. Takes value of a if None.
            origin (list): Please note that you can also pass an
                integer. In this case it is interpreted as the index
                of the atom which is taken as origin.
            outside_sliced (bool): Atoms outside/inside the sphere are
                cut away.
            preserve_bonds (bool): Do not cut covalent bonds.

        Returns:
            Cartesian:
        """
        if origin is None:
            origin = np.zeros(3)
        elif pd.api.types.is_list_like(origin):
            origin = np.array(origin)
        else:
            origin = self.loc[origin, ['x', 'y', 'z']]
        b = a if b is None else b
        c = a if c is None else c

        sides = np.array([a, b, c])
        pos = self.loc[:, ['x', 'y', 'z']]
        if outside_sliced:
            molecule = self[((pos - origin) / (sides / 2)).max(axis=1) < 1.]
        else:
            molecule = self[((pos - origin) / (sides / 2)).max(axis=1) > 1.]

        if preserve_bonds:
            molecule = self._preserve_bonds(molecule)
        return molecule

    def topologic_center(self):
        """Return the average location.

        Args:
            None

        Returns:
            np.array:
        """
        return np.mean(self.loc[:, ['x', 'y', 'z']], axis=0)

    def barycenter(self):
        """Return the mass weighted average location.

        Args:
            None

        Returns:
            np.array:
        """
        try:
            mass = self['mass'].values
        except KeyError:
            mass = self.add_data('mass')['mass'].values
        pos = self.loc[:, ['x', 'y', 'z']].values
        barycenter = (pos * mass[:, None]).sum(axis=0) / self.total_mass()
        return barycenter

    def move(
            self,
            vector=None,
            matrix=None,
            matrix_first=True,
            indices=None,
            copy=False):
        """Move a Cartesian.

        The Cartesian is first rotated, mirrored... by the matrix
        and afterwards translated by the vector.

        Args:
            vector (np.array): default is np.zeros(3)
            matrix (np.array): default is np.identity(3)
            matrix_first (bool): If True the multiplication with the matrix
            is the first operation.
            indices (list): Indices to be moved.
            copy (bool): Atoms are copied or translated to the new location.

        Returns:
            Cartesian:
        """
        output = self.copy()

        indices = self.index if (indices is None) else indices
        vector = np.zeros(3) if vector is None else vector
        matrix = np.identity(3) if matrix is None else matrix
        vectors = output.loc[indices, ['x', 'y', 'z']]

        if matrix_first:
            vectors = np.dot(np.array(matrix), vectors.T).T
            vectors = vectors + np.array(vector)
        else:
            vectors = vectors + np.array(vector)
            vectors = np.dot(np.array(matrix), vectors.T).T

        if copy:
            max_index = self.index.max()
            index_for_copied_atoms = range(max_index + 1,
                                           max_index + len(indices) + 1)
            temp = self.loc[indices, :].copy()
            temp.index = index_for_copied_atoms
            temp[index_for_copied_atoms, ['x', 'y', 'z']] = vectors
            output = output.append(temp)

        else:
            output.loc[indices, ['x', 'y', 'z']] = vectors
        return output

    def bond_lengths(self, indices):
        """Return the distances between given atoms.

        Calculates the distance between the atoms with
        indices ``i`` and ``b``.
        The indices can be given in three ways:

        * As simple list ``[i, b]``
        * As list of lists: ``[[i1, b1], [i2, b2]...]``
        * As :class:`pd.DataFrame` where ``i`` is taken from the index and
          ``b`` from the respective column ``'b'``.

        Args:
            indices (list):

        Returns:
            :class:`numpy.ndarray`: Vector of angles in degrees.
        """
        coords = ['x', 'y', 'z']
        if isinstance(indices, pd.DataFrame):
            i_pos = self.loc[indices.index, coords].values
            b_pos = self.loc[indices.loc[:, 'b'], coords].values
        else:
            indices = np.array(indices)
            if len(indices.shape) == 1:
                indices = indices[None, :]
            i_pos = self.loc[indices[:, 0], coords].values
            b_pos = self.loc[indices[:, 1], coords].values
        return np.linalg.norm(i_pos - b_pos, axis=1)

    def angle_degrees(self, indices):
        """Return the angles between given atoms.

        Calculates the angle in degrees between the atoms with
        indices ``i, b, a``.
        The indices can be given in three ways:

        * As simple list ``[i, b, a]``
        * As list of lists: ``[[i1, b1, a1], [i2, b2, a2]...]``
        * As :class:`pd.DataFrame` where ``i`` is taken from the index and
          ``b`` and ``a`` from the respective columns ``'b'`` and ``'a'``.

        Args:
            indices (list):

        Returns:
            :class:`numpy.ndarray`: Vector of angles in degrees.
        """
        coords = ['x', 'y', 'z']
        if isinstance(indices, pd.DataFrame):
            i_pos = self.loc[indices.index, coords].values
            b_pos = self.loc[indices.loc[:, 'b'], coords].values
            a_pos = self.loc[indices.loc[:, 'a'], coords].values
        else:
            indices = np.array(indices)
            if len(indices.shape) == 1:
                indices = indices[None, :]
            i_pos = self.loc[indices[:, 0], coords].values
            b_pos = self.loc[indices[:, 1], coords].values
            a_pos = self.loc[indices[:, 2], coords].values

        BI, BA = i_pos - b_pos, a_pos - b_pos
        bi, ba = [v / np.linalg.norm(v, axis=1)[:, None] for v in (BI, BA)]
        dot_product = np.sum(bi * ba, axis=1)
        dot_product[dot_product > 1] = 1
        dot_product[dot_product < -1] = -1
        angles = np.degrees(np.arccos(dot_product))
        return angles

    def dihedral_degrees(self, indices, start_row=0):
        """Return the dihedrals between given atoms.

        Calculates the dihedral angle in degrees between the atoms with
        indices ``i, b, a, d``.
        The indices can be given in three ways:

        * As simple list ``[i, b, a, d]``
        * As list of lists: ``[[i1, b1, a1, d1], [i2, b2, a2, d2]...]``
        * As :class:`pandas.DataFrame` where ``i`` is taken from the index and
          ``b``, ``a`` and ``d``from the respective columns
          ``'b'``, ``'a'`` and ``'d'``.

        Args:
            indices (list):

        Returns:
            :class:`numpy.ndarray`: Vector of angles in degrees.
        """
        coords = ['x', 'y', 'z']
        if isinstance(indices, pd.DataFrame):
            i_pos = self.loc[indices.index, coords].values
            b_pos = self.loc[indices.loc[:, 'b'], coords].values
            a_pos = self.loc[indices.loc[:, 'a'], coords].values
            d_pos = self.loc[indices.loc[:, 'd'], coords].values
        else:
            indices = np.array(indices)
            if len(indices.shape) == 1:
                indices = indices[None, :]
            i_pos = self.loc[indices[:, 0], coords].values
            b_pos = self.loc[indices[:, 1], coords].values
            a_pos = self.loc[indices[:, 2], coords].values
            d_pos = self.loc[indices[:, 3], coords].values

        IB = b_pos - i_pos
        BA = a_pos - b_pos
        AD = d_pos - a_pos

        N1 = np.cross(IB, BA, axis=1)
        N2 = np.cross(BA, AD, axis=1)
        n1, n2 = [v / np.linalg.norm(v, axis=1)[:, None] for v in (N1, N2)]

        dot_product = np.sum(n1 * n2, axis=1)
        dot_product[dot_product > 1] = 1
        dot_product[dot_product < -1] = -1
        dihedrals = np.degrees(np.arccos(dot_product))

        # the next lines are to test the direction of rotation.
        # is a dihedral really 90 or 270 degrees?
        # Equivalent to direction of rotation of dihedral
        where_to_modify = np.sum(BA * np.cross(n1, n2, axis=1), axis=1) > 0
        where_to_modify = np.nonzero(where_to_modify)[0]

        length = indices.shape[0] - start_row
        sign = np.full(length, 1, dtype='float64')
        to_add = np.full(length, 0, dtype='float64')
        sign[where_to_modify] = -1
        to_add[where_to_modify] = 360
        dihedrals = to_add + sign * dihedrals
        return dihedrals

    def fragmentate(self, give_only_index=False,
                    use_lookup=settings['defaults']['use_lookup']):
        """Get the indices of non bonded parts in the molecule.

        Args:
            give_only_index (bool): If ``True`` a set of indices is returned.
                Otherwise a new Cartesian instance.
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            list: A list of sets of indices or new Cartesian instances.
        """
        fragments = []
        pending = set(self.index)
        self.get_bonds(use_lookup=use_lookup)

        while pending:
            index = self.connected_to(pick(pending), use_lookup=True,
                                      give_only_index=True)
            pending = pending - index
            if give_only_index:
                fragments.append(index)
            else:
                fragment = self.loc[index]
                fragment._metadata['bond_dict'] = fragment.restrict_bond_dict(
                    self._metadata['bond_dict'])
                try:
                    fragment._metadata['val_bond_dict'] = (
                        fragment.restrict_bond_dict(
                            self._metadata['val_bond_dict']))
                except KeyError:
                    pass
                fragments.append(fragment)
        return fragments

    def restrict_bond_dict(self, bond_dict):
        """Restrict a bond dictionary to self.

        Args:
            bond_dict (dict): Look into :meth:`~chemcoord.Cartesian.get_bonds`,
                to see examples for a bond_dict.

        Returns:
            bond dictionary
        """
        return {j: bond_dict[j] & set(self.index) for j in self.index}

    def get_fragment(self, list_of_indextuples, give_only_index=False,
                     use_lookup=settings['defaults']['use_lookup']):
        """Get the indices of the atoms in a fragment.

        The list_of_indextuples contains all bondings from the
            molecule to the fragment. ``[(1,3), (2,4)]`` means
            for example that the fragment is connected over two
            bonds. The first bond is from atom 1 in the molecule
            to atom 3 in the fragment. The second bond is from atom
            2 in the molecule to atom 4 in the fragment.

        Args:
            list_of_indextuples (list):
            give_only_index (bool): If ``True`` a set of indices
                is returned. Otherwise a new Cartesian instance.
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            A set of indices or a new Cartesian instance.
        """
        exclude = [tuple[0] for tuple in list_of_indextuples]
        index_of_atom = list_of_indextuples[0][1]
        fragment_index = self.connected_to(index_of_atom, exclude=set(exclude),
                                           give_only_index=True,
                                           use_lookup=use_lookup)
        if give_only_index:
            return fragment_index
        else:
            return self.loc[fragment_index, :]

    def without(self, fragments,
                use_lookup=settings['defaults']['use_lookup']):
        """Return self without the specified fragments.

        Args:
            fragments: Either a list of :class:`~chemcoord.Cartesian` or a
                :class:`~chemcoord.Cartesian`.
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            list: List containing :class:`~chemcoord.Cartesian`.
        """
        if pd.api.types.is_list_like(fragments):
            for fragment in fragments:
                try:
                    index_of_all_fragments |= fragment.index
                except NameError:
                    index_of_all_fragments = fragment.index
        else:
            index_of_all_fragments = fragments.index
        missing_part = self.loc[self.index.difference(index_of_all_fragments)]
        missing_part = missing_part.fragmentate(use_lookup=use_lookup)
        return sorted(missing_part, key=lambda x: len(x), reverse=True)

    @staticmethod
    @jit(nopython=True)
    def _jit_pairwise_distances(pos1, pos2):
        """Optimized function for calculating the distance between each pair
        of points in positions1 and positions2.

        Does use python mode as fallback, if a scalar and not an array is
        given.
        """
        n1 = pos1.shape[0]
        n2 = pos2.shape[0]
        D = np.empty((n1, n2))

        for i in range(n1):
            for j in range(n2):
                D[i, j] = np.sqrt(((pos1[i] - pos2[j])**2).sum())
        return D

    def shortest_distance(self, other):
        """Calculate the shortest distance between self and other

        Args:
            Cartesian: other

        Returns:
            tuple: Returns a tuple ``i, j, d`` with the following meaning:

            ``i``:
            The index on self that minimises the pairwise distance.

            ``j``:
            The index on other that minimises the pairwise distance.

            ``d``:
            The distance between self and other. (float)
        """
        coords = ['x', 'y', 'z']
        pos1 = self.loc[:, coords].values
        pos2 = other.loc[:, coords].values
        D = self._jit_pairwise_distances(pos1, pos2)
        i, j = np.unravel_index(D.argmin(), D.shape)
        d = D[i, j]
        i, j = dict(enumerate(self.index))[i], dict(enumerate(other.index))[j]
        return i, j, d

    def inertia(self):
        """Calculate the inertia tensor and transforms along
        rotation axes.

        This function calculates the inertia tensor and returns
        a 4-tuple.

        Args:
            None

        Returns:
            dict: The returned dictionary has four possible keys:

            ``transformed_Cartesian``:
            A frame that is transformed to the basis spanned by
            the eigenvectors of the inertia tensor. The x-axis
            is the axis with the lowest inertia moment, the
            z-axis the one with the highest. Contains also a
            column for the mass

            ``diag_inertia_tensor``:
            A vector containing the sorted inertia moments after
            diagonalization.

            ``inertia_tensor``:
            The inertia tensor in the old basis.

            ``eigenvectors``:
            The eigenvectors of the inertia tensor in the old basis.
        """
        try:
            mass_vector = self.loc[:, 'mass'].values
            molecule = self.copy()
        except KeyError:
            molecule = self.add_data('mass')
            mass_vector = molecule.loc[:, 'mass'].values

        molecule = molecule - molecule.barycenter()
        locations = molecule.loc[:, ['x', 'y', 'z']].values

        diagonals = (np.sum(locations**2, axis=1)[:, None, None]
                     * np.identity(3)[None, :, :])
        dyadic_product = locations[:, :, None] * locations[:, None, :]
        inertia_tensor = (mass_vector[:, None, None]
                          * (diagonals - dyadic_product)).sum(axis=0)
        diag_inertia_tensor, eigenvectors = np.linalg.eig(inertia_tensor)

        # Sort ascending
        sorted_index = np.argsort(diag_inertia_tensor)
        diag_inertia_tensor = diag_inertia_tensor[sorted_index]
        eigenvectors = eigenvectors[:, sorted_index]

        new_basis = eigenvectors
        new_basis = algebra_utilities.orthormalize(new_basis)
        old_basis = np.identity(3)
        Cartesian_mass = self.basistransform(new_basis, old_basis)
        Cartesian_mass = Cartesian_mass - Cartesian_mass.barycenter()

        dic_of_values = {'transformed_Cartesian': Cartesian_mass,
                         'diag_inertia_tensor': diag_inertia_tensor,
                         'inertia_tensor': inertia_tensor,
                         'eigenvectors': eigenvectors}
        return dic_of_values

    def basistransform(
            self, new_basis,
            old_basis=np.identity(3),
            rotate_only=True):
        """Transform the frame to a new basis.

        This function transforms the cartesian coordinates from an
            old basis to a new one. Please note that old_basis and
            new_basis are supposed to have full Rank and consist of
            three linear independent vectors. If rotate_only is True,
            it is asserted, that both bases are orthonormal and right
            handed. Besides all involved matrices are transposed
            instead of inverted.
        In some applications this may require the function
            :func:`algebra_utilities.orthonormalize` as a previous step.

        Args:
            old_basis (np.array):
            new_basis (np.array):
            rotate_only (bool):

        Returns:
            Cartesian: The transformed molecule.
        """
        old_basis = np.array(old_basis)
        new_basis = np.array(new_basis)
        # tuples are extracted row wise
        # For this reason you need to transpose e.g. ex is the first column
        # from new_basis
        if rotate_only:
            ex, ey, ez = np.transpose(old_basis)
            v1, v2, v3 = np.transpose(new_basis)
            assert np.allclose(
                np.dot(old_basis, np.transpose(old_basis)),
                np.identity(3)), 'old basis not orthonormal'
            assert np.allclose(
                np.dot(new_basis, np.transpose(new_basis)),
                np.identity(3)), 'new_basis not orthonormal'
            assert np.allclose(
                np.cross(ex, ey), ez), 'old_basis not righthanded'
            assert np.allclose(
                np.cross(v1, v2), v3), 'new_basis not righthanded'

            basistransformation = np.dot(new_basis, np.transpose(old_basis))
            test_basis = np.dot(np.transpose(basistransformation), new_basis)
            new_cartesian = self.move(matrix=np.transpose(basistransformation))
        else:
            basistransformation = np.dot(new_basis, np.linalg.inv(old_basis))
            test_basis = np.dot(np.linalg.inv(basistransformation), new_basis)
            new_cartesian = self.move(
                matrix=np.linalg.inv(basistransformation))

        assert np.allclose(test_basis, old_basis), "Transformation did'nt work"
        return new_cartesian

    def location(self, indexlist=None):
        """Return the location of an atom.

        You can pass an indexlist or an index.

        Args:
            frame (pd.dataframe):
            indexlist (list): If indexlist is None, the complete index
                is used.

        Returns:
            np.array: A matrix of 3D rowvectors of the location of the
            atoms specified by indexlist. In the case of one index
            given a 3D vector is returned one index.
        """
        indexlist = self.index if indexlist is None else indexlist
        array = self.loc[indexlist, ['x', 'y', 'z']].values
        return array

    def _get_positions(self, indices):
        old_index = self.index
        self.index = range(len(self))
        rename = {j: i for i, j in enumerate(old_index)}

        pos = self.loc[:, ['x', 'y', 'z']].values.astype('f8')
        out = np.empty((len(indices), 3))
        indices = np.array([rename.get(i, i) for i in indices], dtype='i8')

        normal = indices > constants.keys_below_are_abs_refs
        out[normal] = pos[indices[normal]]

        for row, i in zip(np.nonzero(~normal), indices[~normal]):
            out[row] = constants.absolute_refs[i]

        self.index = old_index
        return out

    def distance_to(self,
                    origin=None,
                    other_atoms=None,
                    sort=False):
        """Return a Cartesian with a column for the distance from origin.
        """
        coords = ['x', 'y', 'z']
        norm = np.linalg.norm
        if origin is None:
            origin = np.zeros(3)
        elif pd.api.types.is_list_like(origin):
            origin = np.array(origin)
        else:
            origin = self.loc[origin, ['x', 'y', 'z']]

        if other_atoms is None:
            other_atoms = self.index

        new = self.loc[other_atoms, :].copy()
        try:
            new.loc[:, 'distance'] = norm(new.loc[:, coords] - origin, axis=1)
        except AttributeError:
            # Happens if molecule consists of only one atom
            new.loc[:, 'distance'] = norm(new.loc[:, coords] - origin)
        if sort:
            new.sort_values(by='distance', inplace=True)
        return new

    def change_numbering(self, rename_dict, inplace=False):
        """Return the reindexed version of Cartesian.

        Args:
            rename_dict (dict): A dictionary mapping integers on integers.

        Returns:
            Cartesian: A renamed copy according to the dictionary passed.
        """
        output = self if inplace else self.copy()
        new_index = [rename_dict.get(key, key) for key in self.index]
        output.index = new_index
        if not inplace:
            return output

    def partition_chem_env(self, follow_bonds=4,
                           use_lookup=settings['defaults']['use_lookup']):
        """This function partitions the molecule into subsets of the
        same chemical environment.

        A chemical environment is specified by the number of
        surrounding atoms of a certain kind around an atom with a
        certain atomic number represented by a tuple of a string
        and a frozenset of tuples.
        The ``follow_bonds`` option determines how many branches the
        algorithm follows to determine the chemical environment.

        Example:
        A carbon atom in ethane has bonds with three hydrogen (atomic
        number 1) and one carbon atom (atomic number 6).
        If ``follow_bonds=1`` these are the only atoms we are
        interested in and the chemical environment is::

        ('C', frozenset([('H', 3), ('C', 1)]))

        If ``follow_bonds=2`` we follow every atom in the chemical
        enviromment of ``follow_bonds=1`` to their direct neighbours.
        In the case of ethane this gives::

        ('C', frozenset([('H', 6), ('C', 1)]))

        In the special case of ethane this is the whole molecule;
        in other cases you can apply this operation recursively and
        stop after ``follow_bonds`` or after reaching the end of
        branches.


        Args:
            follow_bonds (int):
            use_lookup (bool): Use a lookup variable for
                :meth:`~chemcoord.Cartesian.get_bonds`.

        Returns:
            dict: The output will look like this::

                { (element_symbol, frozenset([tuples])) : set([indices]) }

                A dictionary mapping from a chemical environment to
                the set of indices of atoms in this environment.
    """
        env_dict = {}

        def get_chem_env(self, i, follow_bonds):
            indices_of_env_atoms = self.connected_to(i,
                                                     follow_bonds=follow_bonds,
                                                     give_only_index=True,
                                                     use_lookup=use_lookup)
            indices_of_env_atoms.remove(i)
            own_symbol, atoms = (
                self.loc[i, 'atom'], self.loc[indices_of_env_atoms, 'atom'])
            environment = collections.Counter(atoms).most_common()
            environment = frozenset(environment)
            return (own_symbol, environment)

        for i in self.index:
            chem_env = get_chem_env(self, i, follow_bonds)
            try:
                env_dict[chem_env].add(i)
            except KeyError:
                env_dict[chem_env] = set([i])
        return env_dict

    def align(self, Cartesian2, ignore_hydrogens=False):
        """Align two Cartesians.

        Searches for the optimal rotation matrix that minimizes
        the RMSD (root mean squared deviation) of ``self`` to
        Cartesian2.
        Returns a tuple of copies of ``self`` and ``Cartesian2`` where
        both are centered around their topologic center and
        ``Cartesian2`` is aligned along ``self``.
        Uses the Kabsch algorithm implemented within
        :func:`~.algebra_utilities.kabsch`

        Args:
            Cartesian2 (Cartesian):
            ignore_hydrogens (bool): Hydrogens are ignored for the
            RMSD.

        Returns:
            tuple:
        """
        coords = ['x', 'y', 'z']
        molecule1 = self.sort_index()
        molecule2 = Cartesian2.sort_index()
        molecule1.loc[:, coords] = (molecule1.loc[:, coords]
                                    - molecule1.topologic_center())
        molecule2.loc[:, coords] = (molecule2.loc[:, coords]
                                    - molecule2.topologic_center())

        if ignore_hydrogens:
            location1 = molecule1.loc[molecule1['atom'] != 'H', coords].values
            location2 = molecule2.loc[molecule2['atom'] != 'H', coords].values
        else:
            location1 = molecule1.loc[:, coords].values
            location2 = molecule2.loc[:, coords].values

        molecule2.loc[:, coords] = algebra_utilities.rotate(location2,
                                                            location1)
        return molecule1, molecule2

    def get_movement_to(self, Cartesian2, step=5, extrapolate=(0, 0)):
        """Return list of Cartesians for the movement from
        self to Cartesian2.

        Args:
            Cartesian2 (Cartesian):
            step (int):
            extrapolate (tuple):

        Returns:
            list: The list contains ``self`` as first and ``Cartesian2``
            as last element.
            The number of intermediate frames is defined by step.
            Please note, that for this reason: len(list) = (step + 1).
            The numbers in extrapolate define how many frames are
            appended to the left and right of the list continuing
            the movement.
        """
        coords = ['x', 'y', 'z']
        difference = Cartesian2.loc[:, coords] - self.loc[:, coords]

        step_frame = difference.copy() / step

        Cartesian_list = []
        temp_Cartesian = self.copy()

        for t in range(-extrapolate[0], step + 1 + extrapolate[1]):
            temp_Cartesian.loc[:, coords] = (
                self.loc[:, coords]
                + step_frame.loc[:, coords] * t)
            Cartesian_list.append(temp_Cartesian.copy())
        return Cartesian_list
