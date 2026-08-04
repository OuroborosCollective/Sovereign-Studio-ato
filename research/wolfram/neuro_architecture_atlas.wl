(*
  Sovereign Neuro-Architecture research foundation.
  This file performs read-only Wolfram entity and graph analysis.
  It does not activate a runtime or establish a biological equivalence claim.
*)

ClearAll[plainValue, regions, regionProperties, regionData, cerebellum,
  cerebellarNeurons, softwareGraph, softwareMetrics, result];

plainValue[value_] := Which[
  Head[value] === Entity, CommonName[value],
  Head[value] === EntityProperty, CanonicalName[value],
  AssociationQ[value], Association @ KeyValueMap[(#1 -> plainValue[#2]) &, value],
  ListQ[value], plainValue /@ value,
  MissingQ[value], ToString[value, InputForm],
  True, value
];

(* FreeformPrompt is intentionally used with literal natural-language input. *)
regions = <|
  "thalamus" -> Quiet @ Check[
    \[FreeformPrompt]["thalamus", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "thalamus"]
  ],
  "hypothalamus" -> Quiet @ Check[
    \[FreeformPrompt]["hypothalamus", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "hypothalamus"]
  ],
  "hippocampus" -> Quiet @ Check[
    \[FreeformPrompt]["hippocampus", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "hippocampus"]
  ],
  "amygdala" -> Quiet @ Check[
    \[FreeformPrompt]["amygdala", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "amygdala"]
  ],
  "cerebellum" -> Quiet @ Check[
    \[FreeformPrompt]["cerebellum", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "cerebellum"]
  ],
  "brainstem" -> Quiet @ Check[
    \[FreeformPrompt]["brainstem", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "brainstem"]
  ],
  "basal ganglia" -> Quiet @ Check[
    \[FreeformPrompt]["basal ganglia", "AnatomicalStructure"],
    Missing["UnresolvedEntity", "basal ganglia"]
  ]
|>;

regionProperties = {
  "CommonName",
  "NeuronalInput",
  "NeuronalOutput",
  "Neurons"
};

regionData = Association @ KeyValueMap[
  Function[{name, entity},
    name -> If[MissingQ[entity],
      entity,
      Quiet @ Check[
        EntityValue[entity, regionProperties, "PropertyAssociation"],
        Missing["EntityValueUnavailable", name]
      ]
    ]
  ],
  regions
];

cerebellum = regions["cerebellum"];
cerebellarNeurons = If[MissingQ[cerebellum],
  {},
  Quiet @ Check[EntityValue[cerebellum, "Neurons"], {}]
];

softwareGraph = Graph[
  {
    "sensory-intake" -> "thalamic-routing",
    "thalamic-routing" -> "reflex-safety",
    "thalamic-routing" -> "deterministic-verification",
    "thalamic-routing" -> "cognitive-side-channel",
    "reflex-safety" -> "evidence",
    "reflex-safety" -> "motor-authorization",
    "deterministic-verification" -> "evidence",
    "deterministic-verification" -> "motor-authorization",
    "cognitive-side-channel" -> "evidence",
    "motor-authorization" -> "cerebellar-correction",
    "motor-authorization" -> "evidence",
    "cerebellar-correction" -> "evidence",
    "evidence" -> "persistence",
    "homeostasis" -> "thalamic-routing",
    "quarantine" -> "evidence"
  },
  DirectedEdges -> True,
  VertexLabels -> "Name"
];

softwareMetrics = <|
  "VertexCount" -> VertexCount[softwareGraph],
  "EdgeCount" -> EdgeCount[softwareGraph],
  "WeaklyConnectedComponents" -> ConnectedComponents[UndirectedGraph[softwareGraph]],
  "BetweennessCentrality" -> AssociationThread[
    VertexList[softwareGraph],
    BetweennessCentrality[softwareGraph]
  ],
  "PageRankCentrality" -> AssociationThread[
    VertexList[softwareGraph],
    PageRankCentrality[softwareGraph]
  ],
  "VertexDegree" -> AssociationThread[
    VertexList[softwareGraph],
    VertexDegree[softwareGraph]
  ]
|>;

result = <|
  "SchemaVersion" -> "sovereign.neuro-wolfram-atlas.v1",
  "EvidenceBoundary" -> <|
    "BiologicalNamesAreAliases" -> True,
    "ArelorianTruthPathModified" -> False,
    "RuntimeActivated" -> False
  |>,
  "ResolvedRegions" -> plainValue[regions],
  "RegionData" -> plainValue[regionData],
  "CerebellarNeuronCount" -> Length[cerebellarNeurons],
  "CerebellarNeurons" -> plainValue[cerebellarNeurons],
  "SoftwareGraphMetrics" -> plainValue[softwareMetrics]
|>;

result
