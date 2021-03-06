import scikit_tt.tensor_train as tt
from scikit_tt.tensor_train import TT
import scikit_tt.utils as utl
from scikit_tt.solvers import sle
import numpy as np
import scipy as sp
import time as _time


def explicit_euler(operator, initial_value, step_sizes, threshold=1e-12, max_rank=50, normalize=1, progress=True):
    """
    Explicit Euler method for linear differential equations in the TT format.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    initial_value : TT
        initial value of the differential equation
    step_sizes : list[float]
        step sizes for the application of the implicit Euler method
    threshold : float, optional
        threshold for reduced SVD decompositions, default is 1e-12
    max_rank : int, optional
        maximum rank of the solution, default is 50
    normalize : {0, 1, 2}, optional
        no normalization if 0, otherwise the solution is normalized in terms of Manhattan or Euclidean norm in each step
    progress : bool, optional
        whether to show the progress of the algorithm or not, default is True

    Returns
    -------
    list[TT]
        numerical solution of the differential equation
    """

    # return current time
    start_time = utl.progress('Running explicit Euler method', 0, show=progress)

    # define solution
    solution = [initial_value]

    # begin explicit Euler method
    # ---------------------------

    for i in range(len(step_sizes)):
        # compute next time step
        tt_tmp = (tt.eye(operator.row_dims) + step_sizes[i] * operator).dot(solution[i])

        # truncate ranks of the solution
        tt_tmp = tt_tmp.ortho(threshold=threshold, max_rank=max_rank)

        # normalize solution
        if normalize > 0:
            tt_tmp = (1 / tt_tmp.norm(p=normalize)) * tt_tmp

        # append solution
        solution.append(tt_tmp.copy())

        # print progress
        utl.progress('Running explicit Euler method', 100 * (i + 1) / len(step_sizes), show=progress,
                     cpu_time=_time.time() - start_time)

    return solution


def errors_expl_euler(operator, solution, step_sizes):
    """
    Compute approximation errors of the explicit Euler method.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    solution : list[TT]
        approximate solution of the linear differential equation
    step_sizes : list[float]
        step sizes for the application of the implicit Euler method

    Returns
    -------
    list[float]
        approximation errors
    """

    # define errors
    errors = []

    # compute relative approximation errors
    for i in range(len(solution) - 1):
        errors.append(
            (solution[i + 1] - (tt.eye(operator.row_dims) + step_sizes[i] * operator).dot(solution[i])).norm() /
            solution[i].norm())

    return errors


def symmetric_euler(operator, initial_value, step_sizes, previous_value=None, threshold=1e-12, max_rank=50, normalize=1, progress=True):
    """
    Time-symmetrized explicit Euler ('second order differencing' in quantum mechanics) for linear differential
    equations in the TT format, see [1]_.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    initial_value : TT
        initial value of the differential equation
    step_sizes : list[float]
        step sizes
    previous_value: TT, optional, default is None
        previous step for symmetric Euler; if not given one explicit Euler step is computed backwards in time
    threshold : float, optional
        threshold for reduced SVD decompositions, default is 1e-12
    max_rank : int, optional
        maximum rank of the solution, default is 50
    normalize : {0, 1, 2}, optional
        no normalization if 0, otherwise the solution is normalized in terms of Manhattan or Euclidean norm in each step
    progress : bool, optional
        whether to show the progress of the algorithm or not, default is True

    Returns
    -------
    list[TT]
        numerical solution of the differential equation

    References
    ----------
    .. [1] A. Askar, A. S. Cakmak, "Explicit integration method for the time-dependent Schrodinger equation for
           collision problems", J. Chem. Phys. 68, 2794, 1978
    """

    # return current time
    start_time = utl.progress('Running time-symmetrized explicit Euler method', 0, show=progress)

    # initialize solution
    solution = [initial_value]

    # begin loop over time steps
    # --------------------------

    for i in range(len(step_sizes)):

        if i == 0: # initialize: one expl. Euler backwards in time if previous step is not given

            if previous_value==None:
                solution_prev = (tt.eye(operator.row_dims) - step_sizes[0]*operator).dot(solution[0])
            else:
                solution_prev = previous_value

            # normalize
            if normalize > 0:
                solution_prev = (1 / solution_prev.norm(p=normalize)) * solution_prev

        else:
            solution_prev = solution[i-1].copy()

        # compute next time step from current and previous time step
        tt_tmp = solution_prev + 2*step_sizes[i]*operator.dot(solution[i])

        # truncate ranks of the solution
        tt_tmp = tt_tmp.ortho(threshold=threshold, max_rank=max_rank)

        # normalize solution
        if normalize > 0:
            tt_tmp = (1 / tt_tmp.norm(p=normalize)) * tt_tmp

        # append solution
        solution.append(tt_tmp.copy())

        # print progress
        utl.progress('Running time-symmetrized explicit Euler method', 100 * (i + 1) / len(step_sizes), show=progress,
                     cpu_time=_time.time() - start_time)

    return solution


def implicit_euler(operator, initial_value, initial_guess, step_sizes, repeats=1, tt_solver='als', threshold=1e-12,
                   max_rank=np.infty, micro_solver='solve', normalize=1, progress=True):
    """
    Implicit Euler method for linear differential equations in the TT format.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    initial_value : TT
        initial value of the differential equation
    initial_guess : TT
        initial guess for the first step
    step_sizes : list[float]
        step sizes for the application of the implicit Euler method
    repeats : int, optional
        number of repeats of the (M)ALS in each iteration step, default is 1
    tt_solver : string, optional
        algorithm for solving the systems of linear equations in the TT format, default is 'als'
    threshold : float, optional
        threshold for reduced SVD decompositions, default is 1e-12
    max_rank : int, optional
        maximum rank of the solution, default is infinity
    micro_solver : string, optional
        algorithm for obtaining the solutions of the micro systems, can be 'solve' or 'lu', default is 'solve'
    normalize : {0, 1, 2}, optional
        no normalization if 0, otherwise the solution is normalized in terms of Manhattan or Euclidean norm in each step
    progress : bool, optional
        whether to show the progress of the algorithm or not, default is True

    Returns
    -------
    list[TT]
        numerical solution of the differential equation
    """

    # return current time
    start_time = utl.progress('Running implicit Euler method', 0, show=progress)

    # define solution
    solution = [initial_value]

    # define temporary tensor train
    tt_tmp = initial_guess

    # begin implicit Euler method
    # ---------------------------

    for i in range(len(step_sizes)):

        # solve system of linear equations for current time step
        if tt_solver == 'als':
            tt_tmp = sle.als(tt.eye(operator.row_dims) - step_sizes[i] * operator, tt_tmp, solution[i],
                             solver=micro_solver, repeats=repeats)
        if tt_solver == 'mals':
            tt_tmp = sle.mals(tt.eye(operator.row_dims) - step_sizes[i] * operator, tt_tmp, solution[i],
                              solver=micro_solver, threshold=threshold, repeats=repeats, max_rank=max_rank)

        # normalize solution
        if normalize > 0:
            tt_tmp = (1 / tt_tmp.norm(p=normalize)) * tt_tmp

        # append solution
        solution.append(tt_tmp.copy())

        # print progress
        utl.progress('Running implicit Euler method', 100 * (i + 1) / len(step_sizes), show=progress,
                     cpu_time=_time.time() - start_time)

    return solution


def errors_impl_euler(operator, solution, step_sizes):
    """
    Compute approximation errors of the implicit Euler method.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    solution : list[TT]
        approximate solution of the linear differential equation
    step_sizes : list[float]
        step sizes for the application of the implicit Euler method

    Returns
    -------
    list[float]
        approximation errors
    """

    # define errors
    errors = []

    # compute relative approximation errors
    for i in range(len(solution) - 1):
        errors.append(
            ((tt.eye(operator.row_dims) - step_sizes[i] * operator).dot(solution[i + 1]) - solution[i]).norm() /
            solution[i].norm())

    return errors


def trapezoidal_rule(operator, initial_value, initial_guess, step_sizes, repeats=1, tt_solver='als', threshold=1e-12,
                     max_rank=np.infty, micro_solver='solve', normalize=1, progress=True):
    """
    Trapezoidal rule for linear differential equations in the TT format.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    initial_value : TT
        initial value of the differential equation
    initial_guess : TT
        initial guess for the first step
    step_sizes : list[float]
        step sizes for the application of the trapezoidal rule
    repeats : int, optional
        number of repeats of the (M)ALS in each iteration step, default is 1
    tt_solver : string, optional
        algorithm for solving the systems of linear equations in the TT format, default is 'als'
    threshold : float, optional
        threshold for reduced SVD decompositions, default is 1e-12
    max_rank : int, optional
        maximum rank of the solution, default is infinity
    micro_solver : string, optional
        algorithm for obtaining the solutions of the micro systems, can be 'solve' or 'lu', default is 'solve'
    normalize : {0, 1, 2}, optional
        no normalization if 0, otherwise the solution is normalized in terms of Manhattan or Euclidean norm in each step
    progress : bool, optional
        whether to show the progress of the algorithm or not, default is True

    Returns
    -------
    list[TT]
        numerical solution of the differential equation
    """

    # return current time
    start_time = utl.progress('Running trapezoidal rule', 0, show=progress)

    # define solution
    solution = [initial_value]

    # define temporary tensor train
    tt_tmp = initial_guess

    # begin trapezoidal rule
    # ----------------------

    for i in range(len(step_sizes)):

        # solve system of linear equations for current time step
        if tt_solver == 'als':
            tt_tmp = sle.als(tt.eye(operator.row_dims) - 0.5 * step_sizes[i] * operator, tt_tmp,
                             (tt.eye(operator.row_dims) + 0.5 * step_sizes[i] * operator).dot(solution[i]),
                             solver=micro_solver, repeats=repeats)
        if tt_solver == 'mals':
            tt_tmp = sle.mals(tt.eye(operator.row_dims) - 0.5 * step_sizes[i] * operator, tt_tmp,
                              (tt.eye(operator.row_dims) + 0.5 * step_sizes[i] * operator).dot(solution[i]),
                              solver=micro_solver, repeats=repeats, threshold=threshold, max_rank=max_rank)

        # normalize solution
        if normalize > 0:
            tt_tmp = (1 / tt_tmp.norm(p=normalize)) * tt_tmp

        # append solution
        solution.append(tt_tmp.copy())

        # print progress
        utl.progress('Running trapezoidal rule', 100 * (i + 1) / len(step_sizes), show=progress,
                     cpu_time=_time.time() - start_time)

    return solution


def errors_trapezoidal(operator, solution, step_sizes):
    """
    Compute approximation errors of the trapezoidal rule.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    solution : list[TT]
        approximate solution of the linear differential equation
    step_sizes : list[float]
        step sizes for the application of the implicit Euler method

    Returns
    -------
    list[float]
        approximation errors
    """

    # define errors
    errors = []

    # compute relative approximation errors
    for i in range(len(solution) - 1):
        errors.append(((tt.eye(operator.row_dims) - 0.5 * step_sizes[i] * operator).dot(solution[i + 1]) -
                       (tt.eye(operator.row_dims) + 0.5 * step_sizes[i] * operator).dot(solution[i])).norm() /
                      ((tt.eye(operator.row_dims) + 0.5 * step_sizes[i] * operator).dot(solution[i])).norm())

    return errors


def adaptive_step_size(operator, initial_value, initial_guess, time_end, step_size_first=1e-10, repeats=1,
                       solver='solve',
                       error_tol=1e-1, closeness_tol=0.5, step_size_min=1e-14, step_size_max=10, closeness_min=1e-3,
                       factor_max=2, factor_safe=0.9, second_method='two_step_Euler', normalize=1, progress=True):
    """
    Adaptive step size method.

    Parameters
    ----------
    operator : TT
        TT operator of the differential equation
    initial_value : TT
        initial value of the differential equation
    initial_guess : TT
        initial guess for the first step
    time_end : float
        time point to which the ODE should be integrated
    step_size_first : float, optional
        first time step, default is 1e-10
    repeats : int, optional
        number of repeats of the ALS in each iteration step, default is 1
    solver : string, optional
        algorithm for obtaining the solutions of the micro systems, can be 'solve' or 'lu', default is 'solve'
    error_tol : float, optional
        tolerance for relative local error, default is 1e-1
    closeness_tol : float, optional
        tolerance for relative change in the closeness to the stationary distribution, default is 0.5
    step_size_min : float, optional
        minimum step size, default is 1e-14
    step_size_max : float, optional
        maximum step size, default is 10
    closeness_min : float, optional
        minimum closeness value, default is 1e-3
    factor_max : float, optional
        maximum factor for step size adaption, default is 2
    factor_safe : float, optional
        safety factor for step size adaption, default is 0.9
    second_method : {'two_step_Euler', 'trapezoidal_rule'}, optional
        which higher-order method should be used, can be 'two_step_Euler' or 'trapezoidal_rule', default is
        'two_step_Euler'
    normalize : {0, 1, 2}, optional
        no normalization if 0, otherwise the solution is normalized in terms of Manhattan or Euclidean norm in each step
    progress : bool, optional
        whether to show the progress of the algorithm or not, default is True

    Returns
    -------
    list[TT]
        numerical solution of the differential equation
    """

    # return current time
    start_time = utl.progress('Running adaptive step size method', 0, show=progress)

    # define solution
    solution = [initial_value]

    # define variable for integration
    t_2 = []

    # set closeness variables
    closeness_pre = (operator.dot(initial_value)).norm()

    # define tensor train for solving the systems of linear equations
    t_tmp = initial_guess

    # set time and step size
    time = 0
    time_steps = [0]
    step_size = step_size_first

    # begin integration
    # -----------------

    while (time < time_end) and (closeness_pre > closeness_min) and (step_size > step_size_min):

        # first method
        t_1 = sle.als(tt.eye(operator.row_dims) - step_size * operator, t_tmp.copy(), solution[-1], solver=solver,
                      repeats=repeats)
        t_1 = (1 / t_1.norm(p=1)) * t_1

        # second method
        if second_method == 'two_step_Euler':
            t_2 = sle.als(tt.eye(operator.row_dims) - 0.5 * step_size * operator, t_tmp.copy(), solution[-1],
                          solver=solver,
                          repeats=repeats)
            t_2 = sle.als(tt.eye(operator.row_dims) - 0.5 * step_size * operator, t_2.copy(), solution[-1],
                          solver=solver,
                          repeats=repeats)
        if second_method == 'trapezoidal_rule':
            t_2 = sle.als(tt.eye(operator.row_dims) - 0.5 * step_size * operator, t_tmp.copy(),
                          (tt.eye(operator.row_dims) + 0.5 * step_size * operator).dot(solution[-1]), solver=solver,
                          repeats=repeats)
        # normalize solution
        if normalize > 0:
            t_2 = (1 / t_2.norm(p=normalize)) * t_2

        # compute closeness to staionary distribution
        closeness = (operator.dot(t_1)).norm()

        # compute relative local error and closeness change
        local_error = (t_1 - t_2).norm() / t_1.norm()
        closeness_difference = (closeness - closeness_pre) / closeness_pre

        # compute factors for step size adaption
        factor_local = error_tol / local_error
        factor_closeness = closeness_tol / np.abs(closeness_difference)

        # compute new step size
        step_size_new = np.amin([factor_max, factor_safe * factor_local, factor_safe * factor_closeness]) * step_size

        # accept or reject step
        if (factor_local > 1) and (factor_closeness > 1):
            time = np.min([time + step_size, time_end])
            step_size = np.amin([step_size_new, time_end - time, step_size_max])
            solution.append(t_1.copy())
            time_steps.append(time)
            t_tmp = t_1
            utl.progress('Running adaptive step size method', 100 * time / time_end, show=progress,
                         cpu_time=_time.time() - start_time)
            closeness_pre = closeness
        else:
            step_size = step_size_new

    return solution, time_steps



def split(S, L, I, M, initial_value, step_size, number_of_steps, threshold=1e-12, max_rank=50, periodic=False):
    """
    Strang splitting for ODEs with SLIM operators.

    Parameters
    ----------
    S : ndarray or list[ndarrays]
        single-site components of SLIM decomposition
    L : ndarray or list[ndarrays]
        left two-site components of SLIM decomposition
    I : ndarray or list[ndarrays]
        identity components of SLIM decomposition
    M : ndarray or list[ndarrays]
        right two-site components of SLIM decomposition
    initial_value : TT
        initial value of the differential equation
    step_size : float
        step size for Strang splitting
    number_of_steps : int
        number of time steps
    threshold : float, optional
        threshold for reduced SVDs, default is 1e-12
    max_rank : int, optional
        maximum rank of the solution, default is 50
    periodic : bool, optional
        whether the SLIM operator is periodic or not, default is False

    Returns
    -------
    list[TT]
        numerical solution of the differential equation
    """

    if len(L.shape) == 2:
        L = L[:,:,None]
        M = M[None, :, :]

    def stage_a():

        # first and third stage (site pairs (0,1), (2,3), ...)
        for j in range(int(np.floor(order/2))):

            # contract cores
            tmp_vec = np.einsum('ijkl,lmno -> ijkmno', tmp.cores[2*j], tmp.cores[2*j+1]).reshape([tmp.ranks[2*j], tmp.row_dims[2*j]*tmp.row_dims[2*j+1], tmp.ranks[2*j+2]])
            tmp_vec = np.einsum('ijk, lj -> ilk', tmp_vec, exp_op_SLM_1).reshape([tmp.ranks[2*j]*tmp.row_dims[2*j], tmp.row_dims[2*j+1]*tmp.ranks[2*j+2]])


            # apply SVD in order to isolate modes
            u, s, v = utl.truncated_svd(tmp_vec, threshold=threshold, max_rank=max_rank)

            # update cores
            tmp.cores[2*j] = u.reshape([tmp.ranks[2*j], tmp.row_dims[2*j], 1, u.shape[1]])
            tmp.cores[2*j+1] = (np.dot(np.diag(s),v)).reshape([u.shape[1], tmp.row_dims[2*j+1], 1, tmp.ranks[2*j+2]])
            tmp.ranks[2*j+1] = u.shape[1]

        # apply single-site operator if chain length is a odd number
        if np.mod(order,2) == 1:
            tmp.cores[-1] = np.einsum('ijkl, mj -> imkl', tmp.cores[-1], exp_op_S_1)

    def stage_b():

        # second stage (site (0) and site pairs (1,2), (3,4), ...)

        # apply single-site operator to first core
        tmp.cores[0] = np.einsum('ijkl, mj -> imkl', tmp.cores[0], exp_op_S_2)

        for j in range(int(np.floor((order-1)/2))):

            # contract cores
            tmp_vec = np.einsum('ijkl,lmno -> ijkmno', tmp.cores[2 * j+1], tmp.cores[2 * j + 2]).reshape([tmp.ranks[2 * j +1] , tmp.row_dims[2 * j +1 ] * tmp.row_dims[2 * j + 2], tmp.ranks[2 * j + 3]])
            tmp_vec = np.einsum('ijk, lj -> ilk', tmp_vec, exp_op_SLM_2).reshape([tmp.ranks[2 * j +1 ] * tmp.row_dims[2 * j + 1], tmp.row_dims[2 * j + 2] * tmp.ranks[2 * j + 3]])

            # apply SVD in order to isolate modes
            u, s, v = utl.truncated_svd(tmp_vec, threshold=threshold, max_rank=max_rank)

            # update cores
            tmp.cores[2 * j + 1] = u.reshape([tmp.ranks[2 * j + 1], tmp.row_dims[2 * j +1], 1, u.shape[1]])
            tmp.cores[2 * j + 2] = (np.dot(np.diag(s),v)).reshape([u.shape[1], tmp.row_dims[2 * j + 2], 1, tmp.ranks[2 * j + 3]])
            tmp.ranks[2 * j + 2] = u.shape[1]

        # apply single-site operator if chain length is a odd number
        if np.mod(order, 2) == 0:
            tmp.cores[-1] = np.einsum('ijkl, mj -> imkl', tmp.cores[-1], exp_op_S_2)



    if periodic:
        print('Warning: periodic boundary conditions are currently ignored!')

    # chain length
    order = initial_value.order

    # define solution list
    solution = []
    solution.append(initial_value)

    if isinstance(S, list):

        print('Warning: only homogeneous chains supported!')

    else: 

        # homogeneous case

        # compute local operators
        d = S.shape[0]
        op_local_SLM = -1j*(np.kron(I, 0.5*S) + np.kron(0.5*S, I) + np.einsum('ijk, klm -> iljm', L, M).reshape([d**2, d**2]))
        op_local_S = -1j*0.5*S

        exp_op_SLM_1 = sp.linalg.expm(op_local_SLM*0.5*step_size)
        exp_op_SLM_2 = sp.linalg.expm(op_local_SLM*step_size)
        exp_op_S_1 = sp.linalg.expm(op_local_S*0.5*step_size)
        exp_op_S_2 = sp.linalg.expm(op_local_S*step_size)

        
        for i in range(number_of_steps):

            # copy previous solution for next step
            tmp = solution[i].copy()

            # Strang splitting
            stage_a()
            stage_b()
            stage_a()

            # append solution
            solution.append(tmp.copy())

    return solution
