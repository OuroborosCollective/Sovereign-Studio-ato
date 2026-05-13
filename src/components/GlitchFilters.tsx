import React from 'react';

const GlitchFilters: React.FC = () => {
  return (
    <svg className="hidden" aria-hidden="true">
      <defs>
        <filter id="organic-fire-filter">
          <feTurbulence type="fractalNoise" baseFrequency="0.01 0.1" numOctaves="2" result="noise" seed="1">
            <animate attributeName="seed" values="1;100;1" dur="0.1s" repeatCount="Infinity" />
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="10" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  );
};

export default GlitchFilters;
