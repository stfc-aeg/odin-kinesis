import React from 'react';
import EncoderStage from './EncoderStage.jsx';

import { TitleCard } from 'odin-react';

function KdcController(props) {
  const {name, motors, kinesisEndPoint} = props;
  
  return (
    <div className="controller">
      Controller: {name}
      {Object.entries(motors).map(([motorName, motorData]) => (
        <EncoderStage
          key={motorName}
          name={motorName}
          data={motorData}
          kinesisEndPoint={kinesisEndPoint}
          dataPath={`controllers/${name}/motors/${motorName}`}
        />
      ))}
    </div>
  );
}

export default KdcController;