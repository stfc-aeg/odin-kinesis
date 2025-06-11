import React, {useState} from 'react';

import { TitleCard, ToggleSwitch, WithEndpoint } from 'odin-react';
import Col from 'react-bootstrap/Col';
import Row from 'react-bootstrap/Row';
import Button from 'react-bootstrap/esm/Button';

import InputGroup from 'react-bootstrap/InputGroup';
import Form from 'react-bootstrap/Form';

const EndPointFormControl = WithEndpoint(Form.Control);
const EndPointToggle = WithEndpoint(ToggleSwitch);
const EndPointButton = WithEndpoint(Button);

function EncoderStage(props){
  const {name, data, kinesisEndPoint, dataPath} = props;

  const [targetPosition, setTargetPosition] = useState(data.position.set_target_pos ?? '');
  const handleTargetChange = (event) => {
    setTargetPosition(event.target.value);
  };

  return (
    <TitleCard title={"Motor "+name}>
    <Row>
      <Col xs={7}>
        <Row>
          <Col xs={6}>
            <InputGroup>
              <InputGroup.Text>Pos.</InputGroup.Text>
                <InputGroup.Text>{data.position.current_pos}</InputGroup.Text>
            </InputGroup>
          </Col>
          <Col xs={6}>
            <InputGroup>
              <InputGroup.Text>Target</InputGroup.Text>
                <Form.Control
                  type="number"
                  value={targetPosition}
                  event_type="enter"
                  onChange={handleTargetChange}
                  disabled={data.moving}
                >
                </Form.Control>
                <EndPointButton
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath+"/position/set_target_pos"}
                  event_type="click"
                  value={targetPosition}
                >
                  Move
                </EndPointButton>

            </InputGroup>
          </Col>
        </Row>
        <Row className='mt-3'>
          <Col>
            details
          </Col>
          <Col>
          Jog settings
            <InputGroup>
              <InputGroup.Text>
                Step
              </InputGroup.Text>
              <EndPointFormControl
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath+"/jog/step_size"}
                  type="number"
                  event_type="enter"
                  value={data.jog.step_size}
              />
            </InputGroup>
            <InputGroup>
              <InputGroup.Text>
                Max vel.
              </InputGroup.Text>
              <EndPointFormControl
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath+"/jog/max_vel"}
                  type="number"
                  event_type="enter"
                  value={data.jog.max_vel}
              />
            </InputGroup>
            <InputGroup>
              <InputGroup.Text>
                Accel.
              </InputGroup.Text>
              <EndPointFormControl
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath+"/jog/accel"}
                  type="number"
                  event_type="enter"
                  value={data.jog.accel}
              />
            </InputGroup>
          </Col>
        </Row>
      </Col>
      <Col xs={5}>
        <Row>
          <Col xs={6} className='mr-3'>
            <Row>
              <EndPointButton
                endpoint={kinesisEndPoint}
                fullpath={dataPath+"/jog/step"}
                event_type="click"
                value={true}
              >
                Step forward
              </EndPointButton>
            </Row>
            <Row className='mt-3'>
            <EndPointButton
                endpoint={kinesisEndPoint}
                fullpath={dataPath+"/jog/step"}
                event_type="click"
                value={false}
            >
              Step backward
            </EndPointButton>
            </Row>
          </Col>
          <Col xs={6} className="ml-2">
            <Row>
              <EndPointButton
                endpoint={kinesisEndPoint}
                fullpath={dataPath+"/position/home"}
                event_type="click"
                value={true}
              >Home</EndPointButton>
            </Row>
            <Row className='mt-3'>
              <EndPointButton
                endpoint={kinesisEndPoint}
                fullpath={dataPath+"/position/stop"}
                event_type="click"
                variant="danger"
                value={true}
              >
                Stop movement
              </EndPointButton>
            </Row>
            <Row>
              Identify
            </Row>
            <Row>
              etc.
            </Row>
          </Col>
        </Row>
      </Col>
    </Row>
    </TitleCard>
  );
}

export default EncoderStage;
