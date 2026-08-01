(* AREKappa Wolfram reference model v0. Research-only, stateless. *)

ClearAll[AREKappaNormalize, AREKappaValidateCoupling, AREKappaReference];

AREKappaNormalize[weights_List, k_Integer : 1000000] := Module[
  {n, total, quotient, remainder, order, result, residual},
  If[weights === {} || !VectorQ[weights, IntegerQ] || Min[weights] < 0,
    Return[Failure["InvalidWeights", <||>]]
  ];
  total = Total[weights];
  If[total <= 0, Return[Failure["ZeroWeightTotal", <||>]]];
  n = Length[weights];
  quotient = Quotient[k weights, total];
  remainder = Mod[k weights, total];
  residual = k - Total[quotient];
  order = SortBy[Range[n], {-remainder[[#]], #} &];
  result = quotient;
  Do[result[[order[[i]]]]++, {i, residual}];
  result
];

AREKappaValidateCoupling[c_, k_Integer : 1000000] := Module[{},
  If[Dimensions[c] =!= {6, 6}, Return[Failure["InvalidDimensions", <||>]]];
  If[!MatrixQ[c, IntegerQ] || Max[Abs[c]] > k,
    Return[Failure["InvalidCoefficient", <||>]]
  ];
  <|
    "RowL1Bound" -> (Max[Total /@ Abs[c]] <= k),
    "RowL1Norms" -> (Total /@ Abs[c])
  |>
];

AREKappaReference[weights_List, coupling_?MatrixQ, k_Integer : 1000000] := Module[
  {rho, couplingCheck, flow},
  rho = AREKappaNormalize[weights, k];
  If[FailureQ[rho], Return[rho]];
  couplingCheck = AREKappaValidateCoupling[coupling, k];
  If[FailureQ[couplingCheck], Return[couplingCheck]];
  flow = coupling . rho;
  <|
    "K" -> k,
    "Rho" -> rho,
    "RhoSum" -> Total[rho],
    "Dimensions" -> {Dimensions[coupling], Dimensions[rho], Dimensions[flow]},
    "Coupling" -> couplingCheck,
    "FlowKappaProduct" -> flow,
    "DeterministicLayers" -> {1, 2, 4, 6},
    "AdvisoryLayers" -> {3, 5}
  |>
];
